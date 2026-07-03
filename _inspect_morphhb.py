import re
import urllib.request

data = urllib.request.urlopen(
    "https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/Exod.xml",
    timeout=60,
).read().decode("utf-8")
idx = data.find('osisID="Exod.25.1"')
print("idx", idx)
open("_exod25_sample.xml", "w", encoding="utf-8").write(data[idx : idx + 1500])
