import os

def folder(base_name, parent_dir="."):
    # Start with the base folder path
    folder_path = os.path.join(parent_dir, base_name)
    counter = 1

    # Loop until we find a folder name that doesn't exist
    while os.path.exists(folder_path):
        folder_path = os.path.join(parent_dir, f"{base_name}_{counter}")
        counter += 1

    # Create the folder
    os.makedirs(folder_path)
    #print(f"Folder created: {folder_path}")

    return folder_path
