"""Project-local content-addressed cache; keep per-export asset inventories."""
from pathlib import Path
import hashlib,os,shutil
def store(root,folder,assets):
    cache=Path(root)/'asset-cache';cache.mkdir(exist_ok=True)
    folder.mkdir(exist_ok=True);hits=0;created=0;manifest={}
    for key,data in assets.items():
        digest=hashlib.sha256(data).hexdigest();cached=cache/(digest+'.png')
        if cached.exists():
            if hashlib.sha256(cached.read_bytes()).hexdigest()!=digest:raise ValueError('素材缓存损坏：'+digest)
            hits+=1
        else:cached.write_bytes(data);created+=1
        dest=folder/(key.replace(':','_')+'.png')
        try:os.link(cached,dest)
        except OSError:shutil.copyfile(cached,dest)
        manifest[key]={'sha256':digest,'bytes':len(data),'file':str(dest.relative_to(root))}
    return {'reused':hits,'created':created,'manifest':manifest}
