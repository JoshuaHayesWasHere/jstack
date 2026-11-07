// The probe's server half, copied into a T3 Code checkout's apps/server by frames.mjs and run
// there: the checkout's own JbusWork, over the same effect/rpc websocket protocol and JSON
// serialization as the server's subscribeJbusWork, with nothing else of the server.
// argv: <port> <jbus root> <home root>
import * as NodeHttp from "node:http";

import * as NodeHttpServer from "@effect/platform-node/NodeHttpServer";
import * as NodeRuntime from "@effect/platform-node/NodeRuntime";
import * as NodeServices from "@effect/platform-node/NodeServices";
import { JbusWorkSnapshot } from "@t3tools/contracts";
import * as Effect from "effect/Effect";
import * as Layer from "effect/Layer";
import * as Schema from "effect/Schema";
import * as Stream from "effect/Stream";
import { HttpRouter } from "effect/http";
import { Rpc, RpcGroup, RpcSerialization, RpcServer } from "effect/rpc";

import * as JbusWork from "../src/jstack/JbusWork.ts";

const [port, jbus, home] = process.argv.slice(2);

const Group = RpcGroup.make(
  Rpc.make("subscribeJbusWork", {
    payload: Schema.Struct({}),
    success: JbusWorkSnapshot,
    stream: true,
  }),
);

const handlers = Group.toLayer(
  Effect.gen(function* () {
    const jbusWork = yield* JbusWork.JbusWork;
    return {
      subscribeJbusWork: () =>
        Stream.unwrap(
          Effect.map(jbusWork.subscribe, ({ latest, changes }) =>
            Stream.concat(Stream.make(latest), changes),
          ),
        ),
    };
  }),
);

const app = RpcServer.layerHttp({
  group: Group,
  path: "/ws",
  protocol: "websocket",
  disableTracing: true,
  disableFatalDefects: true,
}).pipe(
  Layer.provide(handlers),
  Layer.provide(Layer.effect(JbusWork.JbusWork, JbusWork.make({ jbus, home }))),
  Layer.provide(RpcSerialization.layerJson),
);

HttpRouter.serve(app).pipe(
  Layer.provide(NodeHttpServer.layer(NodeHttp.createServer, { port: Number(port) })),
  Layer.provide(NodeServices.layer),
  Layer.launch,
  NodeRuntime.runMain,
);
