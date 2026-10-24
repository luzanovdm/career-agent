// Build-time ICU metadata only; installed runtime never requires Node.
import fs from 'node:fs';
const candidates=[];
for(let a=97;a<=122;a++)for(let b=97;b<=122;b++){
  candidates.push(String.fromCharCode(a,b));
  for(let c=97;c<=122;c++)candidates.push(String.fromCharCode(a,b,c));
}
const rules={};
for(const locale of Intl.PluralRules.supportedLocalesOf(candidates)){
  const resolved=new Intl.PluralRules(locale).resolvedOptions();
  rules[locale]=resolved.pluralCategories;
  rules[resolved.locale]=resolved.pluralCategories;
}
fs.writeFileSync(process.argv[2],JSON.stringify({source:'Node '+process.version+' ICU '+process.versions.icu,kind:'cardinal',rules},null,2)+'\n');
