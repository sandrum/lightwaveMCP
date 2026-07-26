import lwsdk
lwsdk.LWMessageFuncs().info("DIAG2 SCRIPT RAN", None)

OUT_PATH = r"C:\Users\sandr\IdeaProjects\LightwaveMCP\_diag2.txt"
with open(OUT_PATH, "w") as f:
    f.write("diag2 ran\n")
