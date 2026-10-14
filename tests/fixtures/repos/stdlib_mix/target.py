import json
import os
import pathlib
import collections


def work() -> str:
    d = collections.defaultdict(list)
    d["k"].append(json.dumps(os.path.join(str(pathlib.Path("/x")), "y")))
    return d["k"][0]
