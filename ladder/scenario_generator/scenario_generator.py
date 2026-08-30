import argparse
import os
import random
import yaml
import numpy as np
from copy import deepcopy

N = 10  # Number of trials

# ======= DO NOT CHANGE AFTER THIS ======= #


"""
General notes: 
- The doc does not describe the task port, module, names etc correctly, better to just look at tf in Rviz directly !!!

From TF: 

--NIC CARDS: 

---Module names: 
-----nic_card_mount_{x}, where x ∈ {0,1,2,3,4}
-----sc_port_{λ}, where λ  ∈ {0,1}

---Ports: 
-----sfp_port_{λ}, where λ  ∈ {0,1}
-----sc_port_base

SC Elements: 


Plug name tips: 
- "sfp_tip"
- "sc_tip"



CABLES: 
- for sfp ports: "sfp_sc_cable"
- for sc ports: "sfp_sc_cable_reversed"

note: cable_type string under "task" doesn't really matter for engine. 

"""


OUTPUT_DIR = "scenarios"
os.makedirs(OUTPUT_DIR, exist_ok=True)

N_TASKS = 1  # >= 1, tasks per trial

RAILS = {
    "nic_rail": 5,
    "sc_rail": 2,
    "lc_mount_rail": 2,
    "sfp_mount_rail": 2,
    "sc_mount_rail": 2,
}

CABLE_TYPES = ["sfp_sc_cable", "sfp_sc_cable_reversed"]

PLUG_PORT_PAIRS = [
    ("sfp", "sfp_tip", "sfp", "sfp_port_0"),  # doesnt matter now
    ("sc", "sc_tip", "sc", "sc_port_base"),
]


PROFILE_PRESETS = {
    "default": {
        "board_pose": {
            "x": (0.149, 0.171),
            "y": (-0.2, 0.2),
            "z": 1.14,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": (2.9, 3.2),
        },
        "entity_pose": {
            "nic_rail": {
                "translation": (-0.0215, 0.0234),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-10 * (np.pi / 180), 10 * (np.pi / 180)),
            },
            "sc_rail": {
                "translation": (-0.06, 0.055),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
            "lc_mount_rail": {
                "translation": (-0.09425, 0.09425),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 3, np.pi / 3),
            },
            "sfp_mount_rail": {
                "translation": (-0.09425, 0.09425),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 3, np.pi / 3),
            },
            "sc_mount_rail": {
                "translation": (-0.09425, 0.09425),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 3, np.pi / 3),
            },
        },
        "distractor_probability": 0.5,
        "cable_pose": {
            "gripper_offset": {
                "x": (-0.002, 0.002),
                "y_base": 0.015385,
                "y_jitter": (-0.002, 0.002),
                "z_by_type": {
                    CABLE_TYPES[0]: 0.04245,
                    CABLE_TYPES[1]: 0.04045,
                },
                "z_jitter": (-0.002, 0.002),
            },
            "roll": {"base": 0.4432, "jitter": (-0.04, 0.04)},
            "pitch": {"base": -0.4838, "jitter": (-0.04, 0.04)},
            "yaw": {"base": 1.3303, "jitter": (-0.04, 0.04)},
        },
        "target_nic_choices": list(range(5)),
        "target_sc_choices": list(range(2)),
    },
    "curriculum_stage_0": {
        "board_pose": {
            "x": (0.16, 0.16),
            "y": (0.0, 0.0),
            "z": 1.14,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": (3.05, 3.05),
        },
        "entity_pose": {
            rail_name: {
                "translation": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            }
            for rail_name in RAILS
        },
        "distractor_probability": 0.0,
        "cable_pose": {
            "gripper_offset": {
                "x": (0.0, 0.0),
                "y_base": 0.015385,
                "y_jitter": (0.0, 0.0),
                "z_by_type": {
                    CABLE_TYPES[0]: 0.04245,
                    CABLE_TYPES[1]: 0.04045,
                },
                "z_jitter": (0.0, 0.0),
            },
            "roll": {"base": 0.4432, "jitter": (0.0, 0.0)},
            "pitch": {"base": -0.4838, "jitter": (0.0, 0.0)},
            "yaw": {"base": 1.3303, "jitter": (0.0, 0.0)},
        },
        "target_nic_choices": [2],
        "target_sc_choices": [0],
    },
    "curriculum_stage_1": {
        "board_pose": {
            "x": (0.16, 0.16),
            "y": (0.0, 0.0),
            "z": 1.14,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": (3.05, 3.05),
        },
        "entity_pose": {
            "nic_rail": {
                "translation": (-0.01, 0.01),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-5 * (np.pi / 180), 5 * (np.pi / 180)),
            },
            "sc_rail": {
                "translation": (-0.02, 0.02),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
            "lc_mount_rail": {
                "translation": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
            "sfp_mount_rail": {
                "translation": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
            "sc_mount_rail": {
                "translation": (0.0, 0.0),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
        },
        "distractor_probability": 0.0,
        "cable_pose": {
            "gripper_offset": {
                "x": (-0.001, 0.001),
                "y_base": 0.015385,
                "y_jitter": (-0.001, 0.001),
                "z_by_type": {
                    CABLE_TYPES[0]: 0.04245,
                    CABLE_TYPES[1]: 0.04045,
                },
                "z_jitter": (-0.001, 0.001),
            },
            "roll": {"base": 0.4432, "jitter": (-0.01, 0.01)},
            "pitch": {"base": -0.4838, "jitter": (-0.01, 0.01)},
            "yaw": {"base": 1.3303, "jitter": (-0.01, 0.01)},
        },
        "target_nic_choices": list(range(5)),
        "target_sc_choices": list(range(2)),
    },
    "curriculum_stage_2": {
        "board_pose": {
            "x": (0.155, 0.165),
            "y": (-0.05, 0.05),
            "z": 1.14,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": (3.0, 3.1),
        },
        "entity_pose": {
            "nic_rail": {
                "translation": (-0.015, 0.015),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-7 * (np.pi / 180), 7 * (np.pi / 180)),
            },
            "sc_rail": {
                "translation": (-0.03, 0.03),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (0.0, 0.0),
            },
            "lc_mount_rail": {
                "translation": (-0.03, 0.03),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 12, np.pi / 12),
            },
            "sfp_mount_rail": {
                "translation": (-0.03, 0.03),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 12, np.pi / 12),
            },
            "sc_mount_rail": {
                "translation": (-0.03, 0.03),
                "roll": (0.0, 0.0),
                "pitch": (0.0, 0.0),
                "yaw": (-np.pi / 12, np.pi / 12),
            },
        },
        "distractor_probability": 0.25,
        "cable_pose": {
            "gripper_offset": {
                "x": (-0.0015, 0.0015),
                "y_base": 0.015385,
                "y_jitter": (-0.0015, 0.0015),
                "z_by_type": {
                    CABLE_TYPES[0]: 0.04245,
                    CABLE_TYPES[1]: 0.04045,
                },
                "z_jitter": (-0.0015, 0.0015),
            },
            "roll": {"base": 0.4432, "jitter": (-0.02, 0.02)},
            "pitch": {"base": -0.4838, "jitter": (-0.02, 0.02)},
            "yaw": {"base": 1.3303, "jitter": (-0.02, 0.02)},
        },
        "target_nic_choices": list(range(5)),
        "target_sc_choices": list(range(2)),
    },
}


def rand(a, b):
    return float(np.random.uniform(a, b))


def random_bool():
    return bool(random.getrandbits(1))


def choose_index(choices, fixed_value=None):
    if fixed_value is not None:
        return fixed_value
    return random.choice(choices)


def random_board_pose(profile):
    limits = profile["board_pose"]
    return {
        "x": rand(*limits["x"]),
        "y": rand(*limits["y"]),
        "z": limits["z"],
        "roll": limits["roll"],
        "pitch": limits["pitch"],
        "yaw": rand(*limits["yaw"]),
    }


def random_entity_pose(rail_name, profile):
    limits = profile["entity_pose"]
    if rail_name not in limits:
        raise ValueError(f"Unknown rail: {rail_name}")

    l = limits[rail_name]

    return {
        "translation": rand(*l["translation"]),
        "roll": rand(*l["roll"]),
        "pitch": rand(*l["pitch"]),
        "yaw": rand(*l["yaw"]),
    }


def generate_task_board(target_nic, target_sc, profile):
    board = {"pose": random_board_pose(profile)}

    for rail_name, count in RAILS.items():
        for i in range(count):
            key = f"{rail_name}_{i}"

            is_target = (rail_name == "nic_rail" and i == target_nic) or (
                rail_name == "sc_rail" and i == target_sc
            )

            include_distractor = np.random.uniform(0.0, 1.0) < profile["distractor_probability"]
            if is_target or include_distractor:
                board[key] = {
                    "entity_present": True,
                    "entity_name": (
                        f"nic_card_{i}"
                        if rail_name == "nic_rail"
                        else (
                            f"sc_mount_{i}"
                            if rail_name == "sc_rail"
                            else f"{rail_name}_{i}"
                        )
                    ),
                    "entity_pose": random_entity_pose(rail_name, profile),
                }
            else:
                board[key] = {"entity_present": False}

    return board


def generate_cables(cable_names, cable_types, profile):
    cable_pose = profile["cable_pose"]
    offset_cfg = cable_pose["gripper_offset"]
    cables = {}
    for name, ctype in zip(cable_names, cable_types):
        z = offset_cfg["z_by_type"][ctype]
        cables[name] = {
            "pose": {
                "gripper_offset": {
                    "x": rand(*offset_cfg["x"]),
                    "y": offset_cfg["y_base"] + rand(*offset_cfg["y_jitter"]),
                    "z": z + rand(*offset_cfg["z_jitter"]),
                },
                "roll": cable_pose["roll"]["base"] + rand(*cable_pose["roll"]["jitter"]),
                "pitch": cable_pose["pitch"]["base"] + rand(*cable_pose["pitch"]["jitter"]),
                "yaw": cable_pose["yaw"]["base"] + rand(*cable_pose["yaw"]["jitter"]),
            },
            "attach_cable_to_gripper": True,
            "cable_type": ctype,
        }
    return cables


def generate_tasks(cable_names, target_nic, target_sc, plug_type_filter=None):
    tasks = {}
    pair_pool = PLUG_PORT_PAIRS
    if plug_type_filter is not None:
        pair_pool = [pair for pair in PLUG_PORT_PAIRS if pair[0] == plug_type_filter]
    if not pair_pool:
        raise ValueError(f"No plug/port pairs available for plug_type={plug_type_filter!r}")

    for i in range(1, N_TASKS + 1):
        cable_name = random.choice(cable_names)
        plug, plug_name, port, port_name = random.choice(pair_pool)

        if port == "sfp":
            target_module = f"nic_card_mount_{target_nic}"
            port_name = f"sfp_port_{random.choice([0, 1])}"
            cable_type = CABLE_TYPES[0]
        else:
            target_module = f"sc_port_{target_sc}"
            cable_type = CABLE_TYPES[1]

        tasks[f"task_{i}"] = {
            "cable_type": cable_type,  # default name in tasks "sfp_sc"
            "cable_name": cable_name,
            "plug_type": plug,
            "plug_name": plug_name,
            "port_type": port,
            "port_name": port_name,
            "target_module_name": target_module,
            "time_limit": 180,
        }

    return tasks


def generate_trial(trial_id, profile, target_nic_override=None, target_sc_override=None, plug_type_filter=None):
    target_nic = choose_index(profile["target_nic_choices"], target_nic_override)
    target_sc = choose_index(profile["target_sc_choices"], target_sc_override)

    board = generate_task_board(target_nic, target_sc, profile)

    cable_names = [f"cable_{i}" for i in range(N_TASKS)]
    tasks = generate_tasks(cable_names, target_nic, target_sc, plug_type_filter=plug_type_filter)

    cable_types = [task_info["cable_type"] for task_info in tasks.values()]

    cables = generate_cables(cable_names, cable_types, profile)

    return {
        f"trial_{trial_id}": {
            "scene": {"task_board": board, "cables": cables},
            "tasks": tasks,
        }
    }


def generate_scenario(
    num_trials,
    profile,
    target_nic_override=None,
    target_sc_override=None,
    plug_type_filter=None,
):
    scenario = {}
    for i in range(1, num_trials + 1):
        scenario.update(
            generate_trial(
                i,
                profile,
                target_nic_override=target_nic_override,
                target_sc_override=target_sc_override,
                plug_type_filter=plug_type_filter,
            )
        )
    return scenario


class QuotedString(str):
    pass


def quoted_str_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')


yaml.add_representer(QuotedString, quoted_str_representer)


def quote_strings(obj):
    if isinstance(obj, dict):
        return {k: quote_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [quote_strings(i) for i in obj]
    elif isinstance(obj, str):
        return QuotedString(obj)
    else:
        return obj


def parse_args():
    parser = argparse.ArgumentParser(description="Generate AIC scenario YAML.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_PRESETS),
        default="default",
        help="Randomization profile to use. Default preserves current behavior.",
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        default=N,
        help="Number of trials to generate.",
    )
    parser.add_argument(
        "--plug-type",
        choices=["sfp", "sc"],
        default=None,
        help="Restrict generated tasks to a single plug type.",
    )
    parser.add_argument(
        "--target-nic",
        type=int,
        default=None,
        help="Force a specific NIC target index instead of random selection.",
    )
    parser.add_argument(
        "--target-sc",
        type=int,
        default=None,
        help="Force a specific SC target index instead of random selection.",
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help="Output yaml filename inside scenarios/. Defaults to scenario.yaml for default profile and scenario_<profile>.yaml otherwise.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    template_path = "config/config_template.yaml"
    with open(template_path) as f:
        base_yaml = yaml.safe_load(f)

    config = deepcopy(base_yaml)
    profile = PROFILE_PRESETS[args.profile]
    config["trials"] = generate_scenario(
        args.num_trials,
        profile,
        target_nic_override=args.target_nic,
        target_sc_override=args.target_sc,
        plug_type_filter=args.plug_type,
    )
    config = quote_strings(config)

    output_name = args.output_name
    if output_name is None:
        output_name = "scenario.yaml" if args.profile == "default" else f"scenario_{args.profile}.yaml"
    path = output_name if os.path.isabs(output_name) else os.path.join(OUTPUT_DIR, output_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    print(
        "Generated single scenario "
        f"(profile={args.profile}, trials={args.num_trials}, plug_type={args.plug_type or 'mixed'}): {path}"
    )


if __name__ == "__main__":
    main()
