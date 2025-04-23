print("This is top_level_script.py")

# Try importing something from a package
try:
    import pkg_b.module_b
    print("top_level_script successfully imported pkg_b.module_b")
except ImportError:
    print("top_level_script could not import pkg_b.module_b")

# Try importing from a plain script folder (might fail at runtime, but tach should see it)
try:
    from plain_scripts import script_a # Assuming plain_scripts is discoverable
    print("top_level_script successfully imported plain_scripts.script_a")
except (ImportError, ModuleNotFoundError):
    print("top_level_script could not import plain_scripts.script_a") 