print("This is plain_scripts/importer_script.py")

# Import from a regular package
try:
    import pkg_a.module_a
    print("importer_script successfully imported pkg_a.module_a")
    pkg_a.module_a.func_a()
except ImportError:
    print("importer_script could not import pkg_a.module_a") 