from cx_Freeze import setup, Executable

setup(
    name="SpineForgePlanner",
    version="0.4",
    description="Spinal Alignment GUI Tool",
    executables=[Executable("SFP-Ver0.4.py", base="Win32GUI")]
)
