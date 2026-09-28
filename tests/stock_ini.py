"""Read stock INI recipes for installed-game verification."""
from pathlib import Path
import re
from zh.ability_assets import big_entry

def read_ini(folder, name):
    for archive in ('PatchINI.big', 'PatchZH.big', 'INIZH.big'):
        path=Path(folder)/archive
        if path.is_file():
            data=big_entry(path,name)
            if data is not None:return data.decode('cp1252').replace('\r','')
    raise FileNotFoundError(name)

def blocks(text, kind):
    pattern=rf'^{kind}[ \t]+(\w+)[^\n]*\n.*?^End[ \t]*(?:;[^\n]*)?$'
    return {match[1]:match[0] for match in re.finditer(pattern,text,re.M|re.S|re.I)}

def field(text, name):
    match=re.search(rf'^\s*{name}\s*=\s*([^;\n]+)',text,re.M|re.I)
    return match[1].strip() if match else None
