"""The verbs of `jbus item`: propose an item, give it the user's go (`jbus.item.approve`), drop
it, and show one item or list them all."""

from __future__ import annotations

import argparse

import jbus
from jbus import Refused, verbs, wake
from jbus.item import (
    OWNER,
    Verb,
    Where,
    _number,
    approve,
    items,
    judged,
    listed,
    shown,
    write,
)


def _arguments(parser: argparse.ArgumentParser) -> None:
    item_verbs = parser.add_subparsers(dest="verb", required=True)
    where = [str(one) for one in Where if one is not Where.PASS]
    propose = item_verbs.add_parser("propose", help="a new item, with no row", allow_abbrev=False)
    propose.add_argument("--title", required=True)
    propose.add_argument("--by", required=True, help="who proposes it")
    propose.add_argument("--where", choices=where, default="cli", help="where it was said")
    propose.add_argument("--owner", default=OWNER, help="who will do it")
    for name, help in (
        ("approve", "the user's go for an item"),
        ("drop", "an item that will not be done"),
    ):
        one = item_verbs.add_parser(name, help=help, allow_abbrev=False)
        one.add_argument("id")
        one.add_argument("--by", required=True)
        one.add_argument("--where", choices=where, default="cli")
        one.add_argument("--words", default="", help="what was said, as it was said")
        one.add_argument("--seen", help="the last line of the item its writer saw")
    show = item_verbs.add_parser("show", help="an item, its risk and its lines", allow_abbrev=False)
    show.add_argument("id")
    item_verbs.add_parser("list", help="every item, one line each", allow_abbrev=False)


def _item(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state = config.state(project)
    box = wake.Box(state, project)
    if args.verb == "propose":
        made = write(
            state,
            box,
            Verb.PROPOSE,
            by=args.by,
            where=Where(args.where),
            line=f"proposed by {args.by}",
            project=project.name,
            title=args.title,
            owner=args.owner,
        )
        print(f"proposed {made['item']}: {args.title}")
        return 0
    if args.verb == "approve":
        approve(
            state,
            box,
            args.id,
            by=args.by,
            where=args.where,
            words=args.words,
            seen=args.seen,
            user=config.user,
            project=project.name,
        )
        print(f"approved {args.id}")
        return 0
    if args.verb == "drop":
        said = f"drop by {args.by}" + (f": {args.words}" if args.words else "")
        more = {"words": args.words} if args.words else {}
        where = Where(args.where)
        write(
            state,
            box,
            Verb.DROP,
            item=args.id,
            by=args.by,
            where=where,
            line=said,
            seen=args.seen,
            **more,
        )
        print(f"dropped {args.id}")
        return 0
    found = items(state)
    if args.verb == "show":
        if args.id not in found:
            raise Refused(f"refused: there is no item {args.id}")
        print(shown(state, found[args.id]), end="")
        return 0
    for one in sorted(found.values(), key=lambda one: _number(one.id)):
        print(listed(judged(state, one)))
    return 0


VERBS = (verbs.Verb("item", "work items: propose, approve, drop, show, list", _arguments, _item),)
