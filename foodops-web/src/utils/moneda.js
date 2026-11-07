// Formateador único de montos en quetzales.
// No usa Intl con currency GTQ: el símbolo y el formato cambian según el navegador.

/**
 * Formatea un monto como quetzales: "Q1,234.50".
 * Acepta números o cadenas numéricas. null, undefined, '' o valores no numéricos dan "Q0.00".
 * Los negativos llevan el signo antes del símbolo: "-Q5.00".
 */
export function formatQ(valor) {
  const n = typeof valor === 'string' ? Number(valor.trim()) : Number(valor)
  if (valor === null || valor === undefined || valor === '' || !Number.isFinite(n)) return 'Q0.00'

  const [entero, decimales] = Math.abs(n).toFixed(2).split('.')
  const conMiles = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  // Evita "-Q0.00" cuando el valor redondea a cero.
  const signo = n < 0 && Number(Math.abs(n).toFixed(2)) !== 0 ? '-' : ''
  return `${signo}Q${conMiles}.${decimales}`
}
