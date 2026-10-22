# How many times does a failed upload retry?

## Answer
Three times, a second apart, then the upload is reported failed.

## Sources
- `src/upload.py:12` at `3f9c2ab`: "RETRIES = 3"
- `src/upload.py:30-31` at `3f9c2ab`: "time.sleep(1)"

## Confidence
Direct: the constant and the loop that reads it say so.

## Not checked
- whether a caller sets its own count
