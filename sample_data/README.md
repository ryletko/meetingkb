# Sample data

This directory holds tiny, hand-written, non-personal demo fixtures (two English Whisper-JSON transcripts under `transcripts/` and a `terms.txt` listing the demo terms `Alpha`, `Beta`, `Gamma`) so MeetingKB works out of the box without any real meeting recordings; point `KB_DATA_DIR` (and, to get term detection too, `KB_TERMS_FILE=./sample_data/terms.txt`) at this directory and run `kb index --no-opensearch` followed by `kb serve` to explore the app with data already indexed.
