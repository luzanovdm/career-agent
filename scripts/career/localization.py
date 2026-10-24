"""Data-only catalog validation; translations never execute code or HTML."""
import re
from .contracts import require

CATEGORIES={'zero','one','two','few','many','other'}


def locale_tag(value):
    require(isinstance(value,str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',value),'INVALID_LOCALE','Use a bounded BCP47-style locale tag')
    return value


def placeholders(value):
    return set(re.findall(r'\{([A-Za-z][A-Za-z0-9_]*)\}',value))


def validate_catalog(value,english=None):
    require(isinstance(value,dict) and set(value)=={'locale','plural_categories','messages'},'INVALID_CATALOG','Catalog requires locale, plural_categories, messages')
    locale_tag(value['locale']);categories=value['plural_categories'];messages=value['messages']
    require(isinstance(categories,list) and set(categories)<=CATEGORIES and 'other' in categories and len(categories)==len(set(categories)),
            'INVALID_PLURALS','Invalid plural category declaration')
    import json
    from pathlib import Path
    rules=json.loads(Path(__file__).with_name('plural_rules.json').read_text())['rules']
    expected=rules.get(value['locale']) or rules.get(value['locale'].split('-')[0])
    require(expected is not None,'UNSUPPORTED_PLURALS','Locale has no pinned cardinal plural rule metadata; English fallback remains available')
    expected=set(expected)
    require(expected is None or set(categories)==expected,'INVALID_PLURALS','Builtin language plural categories do not match')
    require(isinstance(messages,dict) and 1<=len(messages)<=2000,'INVALID_CATALOG','Catalog requires 1..2000 keys')
    if english is not None:require(set(messages)==set(english['messages']),'CATALOG_COVERAGE','Translation must cover the exact English key set')
    for key,message in messages.items():
        require(isinstance(key,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,150}',key),'INVALID_CATALOG','Invalid translation key')
        base=english['messages'][key] if english else message
        require(isinstance(message,str)==isinstance(base,str),'CATALOG_TYPE','Translation message type changed')
        if isinstance(message,str):variants=[message];base_variants=[base]
        else:
            require(isinstance(message,dict) and set(message)==set(categories),'INVALID_PLURALS','Plural message must cover all declared categories')
            variants=list(message.values());base_variants=list(base.values())
        base_placeholders=set().union(*(placeholders(item) for item in base_variants))
        for item in variants:
            require(isinstance(item,str) and len(item)<=8192 and '<script' not in item.casefold(),'INVALID_CATALOG','Translation values must be bounded plain text')
            require(placeholders(item)==base_placeholders,'CATALOG_PLACEHOLDERS','Translation placeholders differ from English')
            require(item.count('{')==len(re.findall(r'\{[A-Za-z][A-Za-z0-9_]*\}',item)) and item.count('}')==item.count('{'),'INVALID_CATALOG','Only plain named placeholders are supported')
    return value
