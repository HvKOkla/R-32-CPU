import sys
from pathlib import Path

from assembler import R32Assembler
from vm import R32VM

DEFAULT_TEST = "test_v11"

BASE_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = BASE_DIR / "examples"
BUILD_DIR = BASE_DIR / "build"


def run_test(nom_test):
    source_file = EXAMPLES_DIR / f"{nom_test}.r32"
    binary_file = BUILD_DIR / f"{nom_test}.bin"

    print(f"=== Pipeline R-32 : [{nom_test}] ===")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] Assemblage : {source_file} -> {binary_file}")
    if not source_file.exists():
        print(f"      -> ERREUR : fichier source introuvable : {source_file}")
        return False

    assembler = R32Assembler()
    try:
        bytecode = assembler.assemble_file(str(source_file), str(binary_file))
        print(f"      -> OK : {len(bytecode)} mots générés "
              f"({len(bytecode) * 2} octets) + {binary_file.with_suffix('.hex').name} ($readmemh)")
        if assembler.labels:
            print(f"      -> Labels : {assembler.labels}")
    except (ValueError, OSError) as e:
        print(f"      -> ERREUR d'assemblage : {e}")
        return False

    print(f"[2/2] Exécution VM")
    vm = R32VM()
    vm.load_program(bytecode)

    print("--- début ---")
    try:
        steps = vm.run()
        print(f"--- fin ({steps} étapes, PC = {hex(vm.pc)}) ---")
        return True
    except (ValueError, RuntimeError, IndexError) as e:
        print(f"--- ERREUR d'exécution : {e}")
        print(f"    PC = {hex(vm.pc)}  registres = {vm.registers}")
        return False


def main():
    if len(sys.argv) > 1:
        nom_test = sys.argv[1]
    else:
        nom_test = DEFAULT_TEST

    success = run_test(nom_test)
    
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
