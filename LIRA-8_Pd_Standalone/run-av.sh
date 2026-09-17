#!/bin/sh
# Launch the LIRA-8 glitch program at 48 kHz.
#
# The RAVE water model was trained at 48000 Hz. Any other rate shifts its
# pitch by the ratio, a semitone and a half at 44100, so the rate lives here
# rather than in anyone's memory.
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec pd -r 48000 -open "$dir/_LIRA-8.pd" "$@"
