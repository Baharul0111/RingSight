"""Per-field untrusted-text guards; write vocabulary deliberately narrower."""
import html
import re
import unicodedata
CAPS={'memo':300,'finding':1200,'text':1200,'rationale':4000,'reason':1000,'name':120}
ROLE=r'(?:^\s*(?:system|developer)\s*:|\bassistant\s*:|<\||\[/?(?:INST|SYS)\]|</?(?:system|assistant|developer)\b)'
WRITE_PATTERNS=[('role_mimicry',ROLE),('ignore_instructions',r'\bignore\s+(?:(?:all|previous|prior)\s+)+(?:instructions?|prompts?|rules?|messages?|directions?|safety|polic(?:y|ies))\b'),('skip_approval',r'\bskip\s+(?:the\s+)?approval\b')]
READ_PATTERNS=WRITE_PATTERNS+[('ignore_directive',r'\bignore\s+(?:all|previous|prior)\b'),('mark_clean',r'\bmark\b[^.!\n]{0,80}\bclean\b'),('act_on_account',r'\b(?:approve|hold|freeze)\s+(?:this|the)\s+account\b'),('suppress_report',r'\bdo\s+not\s+(?:escalate|report)\b')]
def normalize(text):
    text=unicodedata.normalize('NFKC',str(text))
    return ''.join(c for c in text if c in '\n\t' or unicodedata.category(c)[0]!='C')
def scan(text,profile='read'):
    text=normalize(text)
    return [{'name':name,'span':m.group(0)} for name,pattern in (WRITE_PATTERNS if profile=='write' else READ_PATTERNS) for m in re.finditer(pattern,text,re.I)]
def guard_write(text):return scan(text,'write')
def scrub(text,names=()):
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','<email>',normalize(text))
    text=re.sub(r'(?<![\w-])(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)','<phone>',text)
    for name in sorted(names,key=len,reverse=True):
        if len(name)>2:text=re.sub(r'\b'+re.escape(name)+r'\b','<name>',text,flags=re.I)
    return text

def guard_read(text,field='memo',source='graph'):
    clean=normalize(text)[:CAPS.get(field,300)]
    hits=scan(clean,'read')
    return f'<untrusted field="{html.escape(field)}" source="{html.escape(source)}">{html.escape(clean)}</untrusted>',len(hits)

def guard_text(value,field='memo',source='graph',profile='read'):
    clean=normalize(value)[:CAPS.get(field,300)]
    matches=scan(clean,profile)
    wrapped,_=guard_read(clean,field,source)
    return {'text':wrapped,'guard_hits':len(matches),'matches':matches}
