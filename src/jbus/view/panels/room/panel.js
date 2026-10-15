/* The machine room: the drawer of meters. The room is the machine's, so it has no card of a
   project: the machine's row in the sidebar opens this drawer. */
function meter(label, val, p, lim, text) {
  return '<div class="meter"><div class="lbl"><span>' + esc(label) + '</span><span class="mono">' + esc(val) + '</span></div>' + (p == null ? "" : '<div class="bar"><i style="width:' + Math.min(100, p).toFixed(0) + '%"></i>' + (lim != null ? '<u style="left:' + lim + '%"></u>' : "") + '</div>') + '<div class="src">' + esc(text) + '</div></div>';
}
function dRoom() {
  var r = S.room, l = r.limits, ok = r.answer === "go", plan = r.plan || {}, st = S.jbus.status;
  function planMeter(key, label) { var x = plan[key]; return x && x.used == null ? meter(label, "unknown", null, null, x.say + (ms(x.resets) == null ? "" : ", and its window ended " + day(ms(x.resets)))) : x ? meter(label, x.used + "%", x.used, l.plan, "limit " + l.plan + "%" + (ms(x.resets) == null ? "" : ", resets " + day(ms(x.resets)))) : meter(label, "unknown", null, null, "the limits file does not give it"); }
  return head("Under the line", "Machine room") +
    '<div class="now e-' + (ok ? "ok" : "op") + '"><span class="tag">Read ' + hm(NOW, true) + '</span><span class="big">' + (ok ? "Room to launch" : r.answer === "wait" ? "No room: " + esc(r.why) : esc(r.why)) + '</span><span class="src">The answer is the one <code>jgauge room</code> gives.</span></div>' + note("live") +
    meter("load", (r.load[0] == null ? "unknown" : r.load[0]) + " of " + r.cores + " cores", pct(r.load[0] || 0, r.cores), l.load, "limit " + l.load + "% of cores. 5 and 15 min: " + (r.load[1] == null ? "unknown" : r.load[1]) + ", " + (r.load[2] == null ? "unknown" : r.load[2])) +
    meter("memory free", r.memory_gb == null ? "unknown" : r.memory_gb + " GB", null, null, "needs " + l.memory + " GB. Pressure " + (r.pressure == null ? "unknown" : r.pressure) + ", limit " + l.pressure) +
    planMeter("five_hour", "plan, five hours") + planMeter("seven_day", "plan, seven days") +
    (r.tmp ? meter("/tmp file slots", pct(r.tmp.used, r.tmp.total).toFixed(0) + "% (" + num(r.tmp.used) + " of " + num(r.tmp.total) + ")", pct(r.tmp.used, r.tmp.total), l.slots, "limit " + l.slots + "%") : meter("/tmp file slots", "unknown", null, null, "could not be read")) +
    '<p class="src" style="margin-top:15px">T3 sign-in for jbus expires ' + (ms(st.token_expires) == null ? "unknown" : day(ms(st.token_expires))) + '.</p>';
}
panel({ drawer: dRoom });
