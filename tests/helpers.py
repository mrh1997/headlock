from pathlib import Path

def build_tree(base_dir, tree):
    """
    Build a directory tree ('tree') within a directory ('base_dir').

    content is specified as dictionary of filenames (str) to dict(=subtree) or
    bytes (=file). base_dir has to be a tmpdir object (provided by pytest)
    """
    for sub_name, subtree in tree.items():
        if isinstance(subtree, dict):
            base_dir.mkdir(sub_name)
            build_tree(base_dir.join(sub_name), subtree)
        else:
            base_dir.join(sub_name).write_binary(subtree)
    return Path(base_dir).resolve()