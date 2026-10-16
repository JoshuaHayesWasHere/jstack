1. **First:** read the six tests to confirm they only check the old API's internal call order. If any also cover real observable behavior, keep that part.
2. **Rule followed:** the fourth bullet under **Rule:**: "Update tests to assert the new contract, and delete tests that only protect pre-refactor implementation details."
3. **Find them:** `grep -rnE "assert_has_calls|call_order|mock_calls" tests/` (I'd also search for the deleted API's name) and Read each match.
4. **Pure call-order tests:** delete them, since the new API has no such order to protect. Then run `git rm` or Edit out each test function.
5. **Tests with real behavioral intent:** rewrite them to assert the new API's inputs and outputs. Then run the test suite, e.g. `pytest -q`, and report the actual result.
