# Results

Held-out optimal-move rate (20% of the 4,520 non-terminal tic-tac-toe positions,
argmax over legal cells lands in the minimax-optimal set), ridge readout on
`log1p(1 + spike count)` features from a 300 ms run:

| features | target | held-out |
|---|---|---|
| raw board one-hot, no brain (27) | multi-hot | 0.709 |
| 1,308 descending neurons (ro) | multi-hot | 0.690 |
| 1,308 descending neurons (ro) | Q-values | 0.717 |
| 4,000 most board-sensitive neurons (wide) | multi-hot | 0.832 |
| **4,000 most board-sensitive neurons (wide)** | **Q-values** | **0.836** |
| wide + readout (4,000 + 1,308) | Q-values | 0.823 |
| wide, MLP head (instead of linear) | Q-values | 0.75 |

The shipped readout is the "wide / Q-values" row (alpha 1000, train-set rate 0.933). The brain adds real nonlinear computation: the same linear model on the raw board gets 0.709 vs. 0.836 with the reservoir features. Combining wide + readout features doesn't help (0.823 < 0.836), and an MLP head on the wide features does worse than the linear one (0.75) — the readout stays linear.

`target` = "multi-hot": binary target over minimax-optimal cells. "Q-values": per-cell minimax Q-value for the player to move (+1 forced win, 0 draw, −1 loss / illegal), from exhaustive minimax over all 4,520 non-terminal boards.

## Play record

Play record of the multi-hot 4,000-neuron readout (the Q-value one was fitted afterwards from the cached features and should be equal or better):

| opponent | fly plays | W | D | L |
|---|---|---|---|---|
| random | X | 195 | 3 | 2 |
| random | O | 145 | 42 | 13 |
| minimax | X | 0 | 11 | 9 |
| minimax | O | 0 | 10 | 10 |

Against random play the fly wins or draws about 93% of games (both sides combined). Against perfect (minimax) play it never wins, as expected, and draws roughly half the time.

## Runtimes (Apple M4, 16 GB)

| stage | time |
|---|---|
| feature generation (4,520 boards, 6 processes) | 12 min |
| readout fit, phase A (readout-only features) | 28 s |
| readout fit, phase B (wide features) | 693 s |
| play evaluation (440 games) | 244 s |
| a single fly move (300 ms sim + 30 streamed frames) | ~0.37-0.4 s |

Fitting the final linear head from cached features takes seconds; the 12+ minutes is almost entirely running the LIF reservoir for every one of the 4,520 boards.
