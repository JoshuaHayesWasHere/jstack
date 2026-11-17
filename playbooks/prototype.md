### Prototype

**You own the design decision, not the code. The prototype is a throwaway instrument. The real build follows Feature.**

The one playbook where the Laziness Protocol's "smallest change" and the verification bar invert. Speed over polish, code quality does not matter, no planning. The rigor is in picking the right design cheaply. Propose variations the user didn't ask for, throw an approach away and try another.

1. Scope the decision the prototype exists to make: which layout, which interaction, which density, or for an empirical fork which behavior, timing, or approach. No decision means no prototype. In the **prototype** mode, run Investigation instead. Inside full-stop or full-send, return to the calling playbook.
2. Gather references when the design space is open. Search for prior art, summarize a moodboard of themes, palettes, and layouts, pick the directions yourself and list them in your restatement. Skip when the direction is set.
3. Build throwaway on the route's `proto/` branch. Change production source there only when the route needs it, otherwise use a folder of its own. For a visual decision, vanilla HTML/CSS/JS or the lightest stack that renders the idea, CDN deps, a dev server with hot reload. For a behavioral or timing decision, the smallest script that exercises the question. No production framework, no tests, no abstractions.
4. When variants within one route share a surface, build them behind one switcher (buttons or a keypress), each variant labeled. This is the **exhaust-the-design-space** principle skill made cheap.
5. Verify on the matching surface. For a visual decision, screenshot each variant via the project's verify skill and drive the interaction. For a behavioral or timing decision, observe the thing you are deciding by logging the timing, printing the output, or watching the render. The observation is the test here, not an assertion.
6. Present alternatives, tradeoffs, and a recommendation. The output is the decision plus the throwaway artifact, not shippable code. In the **prototype** mode, hand the chosen direction back through its handoff. Inside full-stop or full-send, pick the winner on the evidence, log it, and resume the calling playbook. The real build follows Feature under **full-stop** or **full-send** (or `architect` for the shape).

**Reply:** the variants explored, the evidence (screenshots for a visual decision, the observed output or timing for a behavioral one), tradeoffs, your recommendation, and the scratch path. Say plainly that the prototype is throwaway.
