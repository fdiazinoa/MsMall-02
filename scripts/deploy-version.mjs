import { readFileSync, writeFileSync } from 'node:fs';

const versionFile = new URL('../VERSION', import.meta.url);
const currentRaw = readFileSync(versionFile, 'utf8').trim();

if (!/^\d+$/.test(currentRaw)) {
  throw new Error(`VERSION inválida: '${currentRaw}'. Debe ser un número entero positivo.`);
}

const current = Number(currentRaw);
const command = process.argv[2] || 'show';

if (command === 'show') {
  console.log(`MsMall v.${current}`);
  process.exit(0);
}

let next;
if (command === 'bump') {
  next = current + 1;
} else if (command === 'set') {
  const requested = String(process.argv[3] || '').trim();
  if (!/^\d+$/.test(requested) || Number(requested) < 1) {
    throw new Error('Uso: npm run deploy:version:set -- <número>');
  }
  next = Number(requested);
} else {
  throw new Error(`Comando no soportado: '${command}'. Use show, bump o set.`);
}

writeFileSync(versionFile, `${next}\n`, 'utf8');
console.log(`Versión de despliegue actualizada: v.${current} → v.${next}`);
