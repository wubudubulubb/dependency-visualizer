import pkg_b.module_b
import pkg_a.sub_a.logic_a

print("Module A imported Module B")
val_a = pkg_a.sub_a.logic_a.get_logic_a_value()
print(f"Module A also got: {val_a}") 