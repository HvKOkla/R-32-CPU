from pathlib import Path

from assembler import R32Assembler
from vm import R32VM


nom_test = "eratosthenes"


BASE_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = BASE_DIR / "examples"
BUILD_DIR = BASE_DIR / "build"


def main():
    source_file = EXAMPLES_DIR / f"{nom_test}.r32"
    binary_file = BUILD_DIR / f"{nom_test}.bin"

    print(f"=== Pipeline R-32 : [{nom_test}] ===")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    
    print(f"[1/2] Assemblage : {source_file} -> {binary_file}")
    if not source_file.exists():
        print(f"      -> ERREUR : fichier source introuvable : {source_file}")
        return

    assembler = R32Assembler()
    try:
        bytecode = assembler.assemble_file(str(source_file), str(binary_file))
        print(f"      -> OK : {len(bytecode)} octets générés")
        if assembler.labels:
            print(f"      -> Labels : {assembler.labels}")
    except (ValueError, OSError) as e:
        print(f"      -> ERREUR d'assemblage : {e}")
        return

    
    print(f"[2/2] Exécution VM")
    vm = R32VM()
    vm.load_program(bytecode)

    print("--- début ---")
    try:
        steps = vm.run()
        print(f"--- fin ({steps} étapes, PC = {hex(vm.pc)}) ---")
    except (ValueError, RuntimeError, IndexError) as e:
        print(f"--- ERREUR d'exécution : {e}")
        print(f"    PC = {hex(vm.pc)}  registres = {vm.registers}")


if __name__ == "__main__":
    main()