"""Simulation settings shared by training (scripts/03_train_readout.py) and serving (fly/server.py).

Chosen from a gain/bias sweep on the real graph (see README "Tuning"):
gain 1 -> activity dies after two hops (GABAergic Pm cells silence the inputs);
gain 2, bias 0 -> ~20% of neurons active, mean rate ~14 Hz, ~550/1308 descending
neurons active, clearly board-dependent activity, ~0.4 s per move on an M4.
"""
GAIN = 2.0          # global multiplier on synaptic weights (Shiu 2024 baseline = 1.0)
BIAS = 0.0          # constant sub-threshold current to every neuron (mV); 0 = only vision drives the brain
DRIVE = 22.0        # input current to driven visual neurons (mV) -> ~100 Hz in isolation
DT = 1.0            # ms
N_STEPS = 300       # 300 ms of brain time per move
FRAME_EVERY = 10    # stream one activity frame per 10 ms of brain time (30 frames/move)
FEATURE = "log1p_counts"
