"""truly top 5 most useful files of all time"""

def format_exc_clean():
    import traceback
    from pathlib import Path
    return traceback.format_exc().replace(str(Path(__file__).resolve().parent.parent).replace('C', 'c'), "DSTS")