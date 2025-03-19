#!/usr/bin/env python3
"""
export_env_variables.py

Description:
    This script reads a .env file and exports its environment variables into a JSON file
    named `advanced_edit.json`, where each variable is formatted as:
    {
        "name": "<ENV_VAR_NAME>",
        "value": "<ENV_VAR_VALUE>",
        "slotSetting": false
    }

    This JSON format is intended for use in **Azure App Service** and **Azure Function Apps**
    under the **Advanced Edit** section of Application Settings. It allows you to quickly 
    migrate or replicate your local environment settings into the cloud service configuration.

    ✔ If `.local/advanced_edit.json` already exists:
        - The script preserves existing variables.
        - For each **duplicate key**, it shows both old and new values and asks whether to overwrite.
        - New variables from `.env` are appended automatically.

Usage:
    From the root of the project (where your `.env` file is located), run:

        python scripts/util/export_env_variables.py

    The output file `advanced_edit.json` will be saved inside the `.local/` folder.
    The folder will be created automatically if it does not exist.

Note:
    - All variables will have `"slotSetting": false` by default.
    - This script is especially useful for deployment pipelines or manual configuration
      in Azure portal's **Advanced Edit** feature of environment variables.
"""

import json
from pathlib import Path

def parse_env_file(env_path):
    env_vars = []
    with open(env_path, "r") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                env_vars.append({
                    "name": key.strip(),
                    "value": value,
                    "slotSetting": False
                })
    return env_vars

def load_existing_json(output_file):
    if output_file.exists():
        with open(output_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Existing JSON is invalid. Starting fresh.")
    return []

def merge_variables(existing_vars, new_vars):
    existing_dict = {var["name"]: var for var in existing_vars}
    for new_var in new_vars:
        name = new_var["name"]
        if name in existing_dict:
            current_value = existing_dict[name]["value"]
            new_value = new_var["value"]
            if current_value != new_value:
                print(f"\n🔁 Variable '{name}' already exists:")
                print(f"    Current value: {current_value}")
                print(f"    New value    : {new_value}")
                choice = input("    👉 Overwrite with new value? [y/N]: ").strip().lower()
                if choice in ("y", "yes"):
                    existing_dict[name]["value"] = new_value
                    print(f"    ✅ Overwritten.")
                else:
                    print(f"    ❌ Kept existing value.")
        else:
            existing_dict[name] = new_var
    return list(existing_dict.values())

def generate_json(env_vars, output_dir=".local", filename="advanced_edit.json"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / filename

    existing_vars = load_existing_json(output_file)
    merged_vars = merge_variables(existing_vars, env_vars)

    with open(output_file, "w") as f:
        json.dump(merged_vars, f, indent=2)

    print(f"\n✅ {filename} saved successfully at {output_file.resolve()}")

if __name__ == "__main__":
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  .env file not found in the current directory.")
    else:
        env_vars = parse_env_file(env_file)
        generate_json(env_vars)
