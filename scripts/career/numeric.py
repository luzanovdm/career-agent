"""Occurrence-scoped numeric evidence. Source strings are data, never instructions."""
from collections import Counter
import json
import re
import unicodedata
from urllib.parse import urlsplit
from .contracts import require, issue

POLICY = 'career-agent.numeric-occurrences/6'
EXTERNAL = frozenset(('resume', 'message', 'answers'))
NUMBER = re.compile(r'(?<!\d)[+\-−]?\d+(?:[.,]\d+)*')
IDENTIFIER = re.compile(r'(?<!\w)[^\W_]+(?:[._-][^\W_]+)*(?!\w)')
# Normalization aliases are not an admission list. Unknown attached units stay quantities.
UNIT_WORDS = (
    ('percent',r'percent(?:age)?s?|процент(?:а|ов)?'),
    ('time:ms',r'milliseconds?|миллисекунд(?:а|ы)?'),
    ('time:s',r'seconds?|secs?|секунд(?:а|ы)?'),
    ('time:min',r'minutes?|mins?|минут(?:а|ы)?'),
    ('time:h',r'hours?|hrs?|час(?:а|ов)?'),
    ('time:day',r'days?|дн(?:я|ей)|день'),
    ('time:week',r'weeks?|недел(?:я|и|ь)'),
    ('time:month',r'months?|месяц(?:а|ев)?'),
    ('time:year',r'years?|yrs?|год(?:а)?|лет'),
    ('count:engineer',r'engineers?|инженер(?:а|ов)?'),
    ('count:person',r'people|persons?|человек(?:а)?'),
    ('mass:kg',r'kilograms?|килограмм(?:а|ов)?'),
    ('mass:g',r'grams?|грамм(?:а|ов)?'),
    ('length:inch',r'inches|inch'),
    ('length:cm',r'centimeters?'),('length:mm',r'millimeters?'),
)
UNIT_SYMBOLS = {'%':'percent','‰':'permille','$':'code:USD','US$':'code:USD','€':'code:EUR','£':'code:GBP',
    'ms':'time:ms','s':'time:s','sec':'time:s','min':'time:min','h':'time:h','hr':'time:h','d':'time:day',
    'wk':'time:week','mo':'time:month','yr':'time:year','kg':'mass:kg','g':'mass:g','cm':'length:cm','mm':'length:mm','мс':'time:ms'}


def normalize_unit(value):
    """One conservative identity contract; unknown symbols/units are preserved, never erased."""
    value=unicodedata.normalize('NFC',value)
    if value in UNIT_SYMBOLS:return UNIT_SYMBOLS[value]
    if re.fullmatch(r'[A-Z]{3}',value):return 'code:'+value
    for normalized,pattern in UNIT_WORDS:
        if re.fullmatch(pattern,value,re.IGNORECASE):return normalized
    return 'opaque:'+value


def _unit_token(value):
    result=''
    for char in value:
        if char.isalpha() or unicodedata.category(char)=='Sc' or char in '%‰°µμ/·^²³':result+=char
        else:break
    return result


# These grammatical followers introduce prose, not a measurement noun. Unknown content
# words are retained as opaque candidates, not claimed to be understood units.
PROSE_FOLLOWERS = frozenset(('and','or','but','nor','yet','then','while','when','where','which','who',
    'that','than','as','at','by','for','from','in','into','of','on','to','until','with','without',
    'is','are','was','were','be','been','being','has','have','had','will','would','can','could',
    'i','we','you','he','she','it','they','a','an','the',
    'и','или','но','а','что','когда','где','который','чем','в','во','на','с','со','до','по','из','от','для',
    'я','мы','вы','он','она','они','это','был','была','были','будет','было',
    'i','lub','ale','w','we','na','do','od','dla','z','ze','jest','był','była','było','były','będzie','ja','my'))
UNIT_OPENERS = frozenset('([{"\'«“‘:=–—-')


def suffix_unit(following):
    """Preserve ambiguous measurement identity across Unicode space and unit wrappers.

    A known grammatical connector stays unitless. An adjacent unknown content word
    remains opaque; matching it is not a semantic assertion that it is a real unit.
    Sentence punctuation before the word is a boundary, not a unit separator.
    """
    value=following.lstrip()
    # Joined punctuation may decorate an explicit suffix; spaced sentence stops do not.
    if value.startswith((',', '_')):value=value[1:].lstrip()
    elif len(value)>1 and value[0]=='.' and bool(_unit_token(value[1:])):value=value[1:]
    for _ in range(4):
        if not value or value[0] not in UNIT_OPENERS:break
        value=value[1:].lstrip()
    suffix=_unit_token(value)
    if not suffix:return None
    normalized=normalize_unit(suffix)
    if normalized.startswith('opaque:') and suffix.casefold() in PROSE_FOLLOWERS:return None
    return normalized


def _enclosing_identifier(text,match):
    left=max(0,match.start()-129);right=min(len(text),match.end()+129)
    for token in IDENTIFIER.finditer(text,left,right):
        if token.start()<=match.start() and token.end()>=match.end() and any(c.isalpha() for c in token.group()):return token
    return None


def quantity_unit(text, match, token=None):
    token=token or _enclosing_identifier(text,match)
    following=text[match.end():match.end()+80];before=text[max(0,match.start()-16):match.start()]
    # Symbols and multipliers are explicit quantity markers, including unknown currencies.
    if following.lstrip().startswith(('%','‰')):return normalize_unit(following.lstrip()[0])
    if re.match(r'\s*[x×](?!\w)',following) or re.search(r'(?<!\w)[x×]$',before):return 'multiplier'
    if before.rstrip() and unicodedata.category(before.rstrip()[-1])=='Sc':return normalize_unit(before.rstrip()[-1])
    prefix=re.search(r'([A-Z]{3})\s*$',before)
    if prefix and (prefix.start()==0 or not before[prefix.start()-1].isalnum()):return normalize_unit(prefix.group(1))
    # Any number-leading alphanumeric token is a quantity/ambiguous measure, even an unseen unit.
    if token and token.start()==match.start():
        suffix=_unit_token(text[match.end():token.end()].lstrip('._-'))
        if suffix:return normalize_unit(suffix)
    # Lowercase unit-before-value notation is conservative ambiguity, not an entity exception.
    if token and token.end()==match.end():
        prefix=text[token.start():match.start()]
        if prefix.isalpha() and (prefix.islower() or len(prefix)==2 and prefix.isupper()):return normalize_unit(prefix)
    if token:return None
    return suffix_unit(following)


def quantity_shaped(value):
    """This classification does not depend on the finite alias catalog."""
    for number in NUMBER.finditer(value):
        if value[0].isdigit() or value[0] in '+-−' or quantity_unit(value,number):return True
    return False


ENTITY_TYPES=r'compan(?:y|ies)|products?|concepts?|tools?|librar(?:y|ies)|technolog(?:y|ies)|frameworks?|projects?|services?|platforms?|identifiers?|terms?|библиотек[а-я]*|компани[а-я]*|продукт[а-я]*|инструмент[а-я]*'


def named_source_entity(source,value):
    """Require an actual naming assertion, named software compound, link or namespace in evidence."""
    escaped=re.escape(value);excerpt=source['excerpt']
    parsed=urlsplit(source['locator'])
    if parsed.scheme in ('http','https') and parsed.hostname:
        host=parsed.hostname.removeprefix('www.')
        if host.casefold()==value.casefold() or host.split('.')[0].casefold()==value.casefold():return True
    if re.search(r'\['+escaped+r'\]\([^\s)]+\)',excerpt,re.IGNORECASE):return True
    # Direct type/name assertions; merely mentioning the token elsewhere is not proof.
    direct=r'(?:'+ENTITY_TYPES+r')\s+(?:(?:named|called)\s+)?[:=]?\s*[`"\']?'+escaped+r'(?!\w)'
    reverse=r'(?<!\w)'+escaped+r'\s+(?:is|—|:)\s+(?:(?:a|an|the|referenced|open-source)\s+)*(?:'+ENTITY_TYPES+r')(?!\w)'
    if re.search(direct,excerpt,re.IGNORECASE) or re.search(reverse,excerpt,re.IGNORECASE):return True
    for sentence in re.split(r'[.!?](?=\s|$)',excerpt):
        if not re.search(r'(?<!\w)'+escaped+r'(?!\w)',sentence,re.IGNORECASE):continue
        if re.search(r'\bnamed\s+(?:'+ENTITY_TYPES+r')(?:\s+(?:and|or)\s+(?:'+ENTITY_TYPES+r'))*\s*:',sentence,re.IGNORECASE):return True
        # e.g. a documented Qwik/D3 interactive game or React/D3 UI, not a price/weight list.
        compound=r'(?:[^\W\d_][\w.-]*/'+escaped+r'|'+escaped+r'/[^\W\d_][\w.-]+)'
        if re.search(compound+r'\s+(?:(?:interactive|web|software|technical|original)\s+)*(?:game|UI|interface|application|stack|library|framework|series)(?!\w)',sentence,re.IGNORECASE):return True
    return False


def candidates(text):
    for match in IDENTIFIER.finditer(text):
        token = match.group()
        if len(token)<=128 and any(char.isalpha() for char in token) and any(char.isdigit() for char in token): yield match


def reference_index(entities=(), sources=(), declared=()):
    """Canonical identity is automatic; an agent declares source-backed reference meaning once."""
    result = {}
    for entity in entities:
        for value in (entity.get('name',''), entity.get('domain') or ''):
            for match in candidates(value):
                result.setdefault(match.group().casefold(), dict(text=match.group(), kind='company', record_id=entity['id'], record_version=entity['version']))
    require(isinstance(declared,(list,tuple)) and len(declared)<=100,'INVALID_REVIEW','Entity references must be bounded')
    by_source={source['id']:source for source in sources}
    for entry in declared:
        require(isinstance(entry,dict) and set(entry)=={'text','source_id'},'INVALID_REVIEW','Entity reference requires text/source_id')
        value=entry['text'];source=by_source.get(entry['source_id'])
        require(isinstance(value,str) and len(value)<=128 and IDENTIFIER.fullmatch(value) and any(c.isalpha() for c in value) and any(c.isdigit() for c in value),
                'INVALID_REVIEW','Entity reference must name one complete alphanumeric identifier')
        require(source and source['readable'] and source['excerpt'].strip(),'ENTITY_REFERENCE_UNVERIFIED','Entity reference needs scoped readable evidence')
        values=[source['excerpt']]
        parsed=urlsplit(source['locator'])
        if parsed.scheme in ('http','https') and parsed.hostname:values.append(parsed.hostname.removeprefix('www.'))
        require(any(match.group().casefold()==value.casefold() for text in values for match in candidates(text)),
                'ENTITY_REFERENCE_UNVERIFIED','Entity reference must occur literally in its saved source')
        require(not quantity_shaped(value),
                'INVALID_REVIEW','A source measurement cannot become a reference exception')
        require(named_source_entity(source,value),'ENTITY_REFERENCE_UNVERIFIED','Saved source does not establish this named entity')
        result.setdefault(value.casefold(),dict(text=value,kind='source',record_id=source['id'],record_version=source['version']))
    return result


def occurrences(text, references=None):
    references = references or {}
    identifiers=list(candidates(text));cursor=0;result=[]
    for match in NUMBER.finditer(text):
        while cursor<len(identifiers) and identifiers[cursor].end()<=match.start(): cursor+=1
        token=identifiers[cursor] if cursor<len(identifiers) and identifiers[cursor].start()<=match.start() and identifiers[cursor].end()>=match.end() else None
        unit=quantity_unit(text,match,token)
        reference=references.get(token.group().casefold()) if token else None
        # Signed values, decimals, measurements and multipliers keep their quantitative role.
        quantitative=unit is not None
        role='reference' if reference and not quantitative else 'quantity'
        result.append(dict(text=match.group(),start=match.start(),end=match.end(),role=role,unit=unit,
                           **dict(reference=reference,entity_start=token.start(),entity_end=token.end()) if role=='reference' else {}))
        require(len(result)<=2048, 'LIMIT_EXCEEDED', 'Numeric occurrences exceed the bounded review limit')
    return result


def number_tokens(text):
    """Raw numeric values; role resolution requires scoped evidence, never global exceptions."""
    return [entry['text'] for entry in occurrences(text)]


def _key(entry): return entry['text'], entry['unit']


def external_measurement_marker(text,start,end):
    """Inspect outside the complete name, rather than after only its numeric prefix."""
    before=text[max(0,start-16):start].rstrip();after=text[end:end+80].lstrip()
    for _ in range(4):
        if before and before[-1] in UNIT_OPENERS:before=before[:-1].rstrip()
        if after and (after[0] in UNIT_OPENERS or after[0] in ')]}»”’'):after=after[1:].lstrip()
    if before.endswith(('%','‰','×')) or after.startswith(('%','‰','×')):return True
    if before and unicodedata.category(before[-1])=='Sc' or after and unicodedata.category(after[0])=='Sc':return True
    if re.search(r'(?<!\w)[x×]\s*$',before) or re.match(r'[x×](?!\w)',after):return True
    outer=before+' 0 '+after;number=NUMBER.match(outer,len(before)+1)
    unit=quantity_unit(outer,number)
    return unit is not None and not unit.startswith('opaque:')


def complete_url_boundary(text,start,end):
    """Only whole locators with matched wrappers and a prose boundary may be exempted."""
    pairs={'(':')','[':']','{':'}','<':'>','"':'"',"'":"'",'“':'”','‘':'’','«':'»'}
    if start and not text[start-1].isspace() and text[start-1] not in pairs:return False
    # Enclosing prose/Markdown wrappers may open before introductory words, not
    # just directly before the locator. Keep a bounded unmatched delimiter stack.
    stack=[];prefix=text[:start]
    for index,char in enumerate(prefix):
        if char in ('"',"'") and stack and stack[-1]==char:
            stack.pop()
        elif char=="'" and index and prefix[index-1].isalnum():
            continue  # A prose apostrophe is not an opening quotation mark.
        elif char in pairs:
            if len(stack)>=64:return False
            stack.append(pairs[char])
        elif char in pairs.values():
            if stack and stack[-1]==char:stack.pop()
            else:stack.clear()  # A prior unrelated unmatched closer has no scope.
    expected=list(reversed(stack))
    right=end
    while right<len(text) and not text[right].isspace():
        char=text[right]
        if char in pairs.values():
            if not expected or expected.pop(0)!=char:return False
        elif char not in '.,;!?:':return False
        right+=1
    return True


def explicit_entities(documents, review, references, sources, entities):
    """Optional agent disambiguation of exact identifiers; quantities cannot be relabeled wholesale."""
    spans = review.get('entity_spans', [])
    require(isinstance(spans,list) and len(spans)<=100, 'INVALID_REVIEW', 'Entity spans must be bounded')
    result=[];by_slot={doc['slot']:doc['text'] for doc in documents};by_source={source['id']:source for source in sources};by_entity={entity['id']:entity for entity in entities}
    for span in spans:
        require(isinstance(span,dict) and set(span) in ({'slot','start','end','text','source_id'},{'slot','start','end','text','company_id'}), 'INVALID_REVIEW', 'Entity span requires slot/start/end/text and one existing source/company reference')
        start,end=span['start'],span['end'];value=span['text'];text=by_slot.get(span['slot'])
        require(type(start) is int and type(end) is int and isinstance(value,str) and text is not None and 0<=start<end<=len(text) and text[start:end]==value,
                'INVALID_REVIEW', 'Entity span must bind exact saved document text')
        if value.startswith(('http://','https://')):
            source=by_source.get(span.get('source_id'))
            try:
                parsed=urlsplit(value);port=parsed.port
                valid=bool(parsed.hostname and not parsed.username and not parsed.password)
            except ValueError:valid=False
            require(valid and len(value)<=4096 and not re.search(r'[\s<>"\\\\]|%(?![0-9a-fA-F]{2})',value),
                    'INVALID_REVIEW','URL reference requires one complete ordinary HTTP(S) locator')
            require(source and source['readable'] and source['excerpt'].strip() and source['locator']==value,
                    'ENTITY_REFERENCE_UNVERIFIED','URL span needs its exact scoped readable source locator')
            # A partial URL cannot hide a path/query continuation outside the declared span.
            require(complete_url_boundary(text,start,end),'INVALID_REVIEW','URL span must cover the complete literal locator without a hidden continuation')
            require(not external_measurement_marker(text,start,end),'INVALID_REVIEW','An external measurement marker cannot be hidden by a URL span')
            result.append(dict(slot=span['slot'],start=start,end=end,url=True,reference=dict(text=value,kind='source',record_id=source['id'],record_version=source['version'],reference_type='url')))
            continue
        require(IDENTIFIER.fullmatch(value) and any(c.isalpha() for c in value) and any(c.isdigit() for c in value), 'INVALID_REVIEW', 'Entity span must cover one complete alphanumeric identifier')
        require(any(token.start()==start and token.end()==end for token in candidates(text)), 'INVALID_REVIEW', 'Entity span cannot hide part of a larger token')
        if 'source_id' in span:
            source=by_source.get(span['source_id'])
            require(source and source['readable'] and source['excerpt'].strip() and any(match.group().casefold()==value.casefold() for match in candidates(source['excerpt'])),
                    'ENTITY_REFERENCE_UNVERIFIED', 'Entity span needs its scoped readable literal source')
            ref=dict(text=value,kind='source',record_id=source['id'],record_version=source['version'])
            require(named_source_entity(source,value), 'ENTITY_REFERENCE_UNVERIFIED', 'Source does not establish this named entity')
        else:
            entity=by_entity.get(span['company_id'])
            require(entity and any(match.group().casefold()==value.casefold() for field in (entity['name'],entity.get('domain') or '') for match in candidates(field)), 'ENTITY_REFERENCE_UNVERIFIED', 'Entity span needs an exact canonical company identifier')
            ref=dict(text=value,kind='company',record_id=entity['id'],record_version=entity['version'])
        require(not external_measurement_marker(text,start,end), 'INVALID_REVIEW', 'An external measurement marker cannot be hidden by an entity span')
        for number in NUMBER.finditer(text):
            if number.start()<end and start<number.end():
                require(start<=number.start() and number.end()<=end, 'INVALID_REVIEW', 'An entity span cannot hide an external numeric sign')
                local=NUMBER.match(value,number.start()-start)
                require(local and quantity_unit(text,number)==quantity_unit(value,local), 'INVALID_REVIEW', 'An external measurement marker cannot be hidden by an entity span')
        result.append(dict(slot=span['slot'],start=start,end=end,reference=ref))
    return result


def numeric_review(documents, claims, review, answers=(), entities=(), sources=()):
    """Each permitted quantity belongs to its actual mapped claim/value range, not to a global set."""
    references=reference_index(entities,sources,review.get('entity_refs',[]));overrides=explicit_entities(documents,review,references,sources,entities)
    docs={doc['slot']:doc['text'] for doc in documents if doc['slot'] in EXTERNAL}
    indexed={slot:occurrences(text,references) for slot,text in docs.items()};supported=set();by_claim={claim['id']:claim for claim in claims}
    require(sum(len(entries) for entries in indexed.values())<=2048,'LIMIT_EXCEEDED','Numeric packet audit exceeds its bound')
    for span in overrides:
        for entry in indexed.get(span['slot'],[]):
            if span['start']<=entry['start'] and entry['end']<=span['end']:
                entry['explicit_reference']=span['reference']
                entry['url_reference']=span.get('url',False)
    for span in review['claim_spans']:
        claim=by_claim[span['claim_id']];wording=span['text']
        budgets=[]
        for value in (claim['assertion'],claim['meaning']):budgets.append(Counter(_key(n) for n in occurrences(value,references) if n['role']=='quantity'))
        budget=budgets[0]|budgets[1]
        for slot,text in docs.items():
            start=text.find(wording)
            while start>=0:
                available=budget.copy()
                for entry in indexed[slot]:
                    if entry['role']=='quantity' and start<=entry['start'] and entry['end']<=start+len(wording) and available[_key(entry)]:
                        available[_key(entry)]-=1;supported.add((slot,entry['start'],entry['end']))
                start=text.find(wording,start+len(wording))
    for slot,entries in indexed.items():
        for entry in entries:
            if 'explicit_reference' not in entry:continue
            reference=entry.pop('explicit_reference')
            require(entry.pop('url_reference',False) or entry['unit'] is None or (slot,entry['start'],entry['end']) in supported,
                    'ENTITY_REFERENCE_UNVERIFIED','A unit-shaped name needs independently grounded claim support at this exact occurrence')
            entry.update(role='reference',unit=None,reference=reference)
    # Contact values are exact literal occurrences. An unrelated equal digit does not reuse a phone/email.
    for answer in answers:
        if not answer['meaning'].startswith(('contact.','compensation.external')) or answer['disposition']!='answered': continue
        value=answer['value']
        if isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:pass
        literals=[value] if isinstance(value,str) else [item for item in value.values() if isinstance(item,str)] if isinstance(value,dict) else []
        for value in literals:
            if not value or len(value)>512:continue
            # Scalar short numeric responses need a field-bound span, not a packet-wide number grant.
            if re.fullmatch(r'[\d.,+\-−\s]+',value) and sum(c.isdigit() for c in value)<7:continue
            for slot,text in docs.items():
                start=text.find(value)
                while start>=0:
                    for entry in indexed[slot]:
                        if start<=entry['start'] and entry['end']<=start+len(value) and entry['unit'] is None: supported.add((slot,entry['start'],entry['end']))
                    start=text.find(value,start+len(value))
    # Phone formatting can vary without changing the exact current scoped number.
    for answer in answers:
        if not answer['meaning'].startswith('contact.phone') or answer['disposition']!='answered':continue
        value=answer['value']
        if isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:pass
        values=[value] if isinstance(value,str) else [item for item in value.values() if isinstance(item,str)] if isinstance(value,dict) else []
        digits={''.join(char for char in value if char.isdigit()) for value in values if 7<=sum(char.isdigit() for char in value)<=20}
        for slot,text in docs.items():
            for match in re.finditer(r'(?<!\w)\+?\d[\d ()+.-]{5,38}\d(?!\w)',text):
                if ''.join(char for char in match.group() if char.isdigit()) not in digits:continue
                for entry in indexed[slot]:
                    if match.start()<=entry['start'] and entry['end']<=match.end() and entry['unit'] is None:supported.add((slot,entry['start'],entry['end']))
    answer_spans=review.get('answer_spans',[])
    require(isinstance(answer_spans,list) and len(answer_spans)<=100,'INVALID_REVIEW','Answer spans must be bounded')
    by_answer={answer['id']:answer for answer in answers}
    for span in answer_spans:
        require(isinstance(span,dict) and set(span)=={'answer_id','text'} and isinstance(span['text'],str) and span['text'], 'INVALID_REVIEW', 'Answer span requires answer_id/text')
        answer=by_answer.get(span['answer_id'])
        require(answer and answer['disposition']=='answered' and answer['meaning'].startswith(('contact.','compensation.external')), 'UNSUPPORTED_ANSWER', 'Numeric answer span requires an applicable actual external response')
        raw=answer['value']
        if isinstance(raw,str):
            try:raw=json.loads(raw)
            except ValueError:pass
        units=answer.get('units',{})
        if isinstance(units,str):
            try:units=json.loads(units)
            except ValueError:units={}
        values=[raw] if isinstance(raw,(str,int,float)) else list(raw.values()) if isinstance(raw,dict) else []
        source=' '.join(str(value) for value in values)
        allowed=Counter(_key(entry) for entry in occurrences(source) if entry['role']=='quantity')
        currency=units.get('currency') if isinstance(units,dict) else None
        if isinstance(currency,str) and re.fullmatch(r'[A-Za-z]{3}',currency):
            allowed=Counter((value,unit or normalize_unit(currency.upper())) for value,unit in allowed.elements())
        found=False
        for slot,text in docs.items():
            start=text.find(span['text'])
            while start>=0:
                found=True;available=allowed.copy()
                for entry in indexed[slot]:
                    if start<=entry['start'] and entry['end']<=start+len(span['text']) and available[_key(entry)]:
                        available[_key(entry)]-=1;supported.add((slot,entry['start'],entry['end']))
                start=text.find(span['text'],start+len(span['text']))
        require(found,'UNSUPPORTED_ANSWER','Answer span must bind actual external text')
    issues=[];audit=[]
    for slot,entries in indexed.items():
        for entry in entries:
            audit.append(dict(slot=slot,supported=entry['role']=='reference' or (slot,entry['start'],entry['end']) in supported,**entry))
            if entry['role']=='quantity' and (slot,entry['start'],entry['end']) not in supported:
                issues.append(dict(issue('UNMATCHED_NUMBER','Unmatched numerical assertion: '+entry['text']),slot=slot,start=entry['start'],end=entry['end'],token=entry['text'],role='quantity',unit=entry['unit'],offset_unit='unicode_code_points'))
    return issues,dict(policy=POLICY,offset_unit='unicode_code_points',occurrences=audit)
