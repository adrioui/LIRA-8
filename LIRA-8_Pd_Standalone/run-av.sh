#!/bin/sh
# Launch the LIRA-8 glitch program at 48 kHz.
#
# The RAVE water model was trained at 48000 Hz. Any other rate shifts its
# pitch by the ratio, a semitone and a half at 44100, so the rate lives here
# rather than in anyone's memory.
#
# libtorch busy-spins its thread pool while idle and pins multiple cores for
# nothing. These variables make the pool sleep instead. Without them the
# patch burns around 250 percent CPU from the moment the model loads, even
# with the WATER toggle off and no audio flowing.
export KMP_BLOCKTIME=0
export KMP_AFFINITY=disabled
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
# A bigger audio buffer survives the CPU bursts from torch inference without
# audible dropouts. The cost is latency, which this drone-and-visuals program
# tolerates better than stutter. Lower it if key response feels slow.
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec pd -r 48000 -audiobuf 100 -open "$dir/_LIRA-8.pd" "$@"
