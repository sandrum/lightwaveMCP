import lwsdk
OUT_PATH = r"C:\Users\sandr\IdeaProjects\LightwaveMCP\_diag_min2.txt"
f = open(OUT_PATH, "w")
f.write("hello from lw_diag_min2, lwsdk=%r\n" % (lwsdk,))
f.close()
