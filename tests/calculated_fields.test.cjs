const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const mod = {};
new Function('exports', ts.transpileModule(fs.readFileSync('utils/calculatedFields.ts','utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(mod);
const config = operator => ({_total_bruto_calc_left:'Neto',_total_bruto_calc_right:'Impuesto',_total_bruto_calc_operator:operator});
test('preview supports all four source-column operations',()=>{
  for(const [operator,expected] of [['+','12'],['-','8'],['*','20'],['/','5']]) assert.equal(mod.calculatedPreview('total_bruto',{Neto:'10',Impuesto:'2'},config(operator)),expected);
});
test('preview validates zero division and invalid operands',()=>{
  assert.equal(mod.calculatedPreview('total_bruto',{Neto:'10',Impuesto:'0'},config('/')),'División entre cero');
  assert.match(mod.calculatedPreview('total_bruto',{Neto:'bad',Impuesto:'2'},config('+')),/no numérico/);
});
test('preview respects locale and native JSON numbers',()=>{
  const constants={...config('+'),_decimal_separator:','};
  assert.equal(mod.calculatedPreview('total_bruto',{Neto:'100,50',Impuesto:'18,09'},constants),'118.59');
  assert.equal(mod.calculatedPreview('total_bruto',{Neto:10.5,Impuesto:1.5},constants),'12');
});
