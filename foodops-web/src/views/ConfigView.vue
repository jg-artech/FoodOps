<template>
  <div class="max-w-2xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-800">Configuración</h1>
      <RouterLink to="/pos" class="text-sm text-gray-500 hover:text-gray-700">← POS</RouterLink>
    </div>

    <!-- Pestañas -->
    <div class="flex gap-2 mb-6 overflow-x-auto pb-1">
      <button v-for="t in tabs" :key="t.key" @click="tab = t.key"
        class="px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition"
        :class="tab === t.key ? 'bg-orange-500 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:border-orange-300'">
        {{ t.label }}
      </button>
    </div>

    <!-- ═══ PESTAÑA: MENÚ ═══ -->
    <div v-if="tab === 'menu'">
      <div v-for="cat in categorias" :key="cat.key" class="bg-white rounded-2xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
        <div class="flex items-center justify-between px-5 py-3 bg-gray-50 border-b border-gray-200">
          <h3 class="font-bold text-gray-700">{{ cat.emoji }} {{ cat.label }}</h3>
          <button @click="abrirNuevo(cat.key)"
            class="text-xs bg-orange-500 hover:bg-orange-600 text-white px-3 py-1.5 rounded-full font-semibold transition">
            + Agregar
          </button>
        </div>
        <div class="divide-y divide-gray-100">
          <div v-for="item in itemsPorCategoria(cat.key)" :key="item.id" class="px-5 py-3">
            <div class="flex items-center gap-3">
              <button @click="cambiarEmoji(item)" class="text-2xl hover:scale-110 transition-transform">{{ item.emoji }}</button>
              <input v-model="item.nombre"
                class="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 font-medium" />
              <div class="flex items-center gap-1 shrink-0">
                <span class="text-xs text-gray-400">Q</span>
                <input v-model.number="item.precio" type="number" min="0"
                  class="w-20 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 font-bold text-orange-600" />
              </div>
              <button @click="eliminarItem(item.id)" class="text-red-400 hover:text-red-600 text-lg px-1 transition">✕</button>
            </div>
            <div v-if="item.categoria === 'combos'" class="mt-2 ml-9">
              <input v-model="item.contenido" placeholder="Contenido del combo..."
                class="w-full border border-gray-100 rounded-lg px-2 py-1.5 text-xs text-gray-600 focus:outline-none focus:ring-1 focus:ring-orange-300 bg-gray-50" />
            </div>
            <div class="mt-1 ml-9">
              <input v-model="item.unidad" placeholder="pieza / lb / porción"
                class="border border-gray-100 rounded-lg px-2 py-1 text-xs text-gray-400 focus:outline-none focus:ring-1 focus:ring-orange-200 bg-gray-50 w-28" />
            </div>
          </div>
        </div>
        <div v-if="itemsPorCategoria(cat.key).length === 0" class="px-5 py-4 text-sm text-gray-400 text-center">
          Sin productos — usa + Agregar
        </div>
      </div>

      <!-- Nueva categoría -->
      <div class="bg-white rounded-2xl border border-dashed border-gray-300 p-5 mb-5">
        <h3 class="font-bold text-gray-500 text-sm mb-3">+ Nueva categoría</h3>
        <div class="flex gap-2">
          <input v-model="nuevaCat.key" placeholder="clave (ej: bebidas)" autocomplete="off"
            class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          <input v-model="nuevaCat.label" placeholder="nombre (ej: Bebidas)" autocomplete="off"
            class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          <input v-model="nuevaCat.emoji" placeholder="🥤" maxlength="4"
            class="w-14 border border-gray-200 rounded-lg px-2 py-2 text-sm text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
          <button @click="agregarCategoria" class="bg-gray-700 hover:bg-gray-800 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
            Crear
          </button>
        </div>
      </div>

      <p v-if="guardadoMenu" class="text-green-600 text-sm text-center font-semibold mb-3">✓ Menú guardado</p>
      <div class="flex gap-3">
        <button @click="guardarMenu" class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition">
          💾 Guardar menú
        </button>
        <button @click="resetearMenu" class="border border-gray-300 text-gray-500 text-sm px-4 py-3 rounded-xl hover:bg-gray-50 transition">
          Restablecer
        </button>
      </div>
    </div>

    <!-- ═══ PESTAÑA: COSTOS ═══ -->
    <div v-if="tab === 'costos'">
      <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5 text-sm text-amber-800">
        <p class="font-bold mb-1">¿Para qué sirven los costos?</p>
        <p>Define el costo de cada producto para calcular el <strong>margen de ganancia</strong>. Los <strong>combos</strong> tienen desglose de ingredientes para mayor precisión.</p>
      </div>

      <div v-for="cat in categorias" :key="cat.key" class="bg-white rounded-2xl border border-gray-200 shadow-sm mb-4 overflow-hidden">
        <div class="px-5 py-3 bg-gray-50 border-b border-gray-200">
          <h3 class="font-bold text-gray-700">{{ cat.emoji }} {{ cat.label }}</h3>
        </div>
        <div class="divide-y divide-gray-100">

          <!-- Productos simples (no combo) -->
          <template v-if="cat.key !== 'combos'">
            <div v-for="item in itemsPorCategoria(cat.key)" :key="item.id"
              class="px-5 py-3 flex items-center gap-3">
              <span class="text-xl shrink-0">{{ item.emoji }}</span>
              <span class="flex-1 text-sm text-gray-700 font-medium">{{ item.nombre }}</span>
              <span class="text-sm text-orange-500 font-bold w-16 text-right shrink-0">Q{{ item.precio }}</span>
              <div class="flex items-center gap-1 shrink-0">
                <span class="text-xs text-gray-400">Costo Q</span>
                <input v-model.number="costos[item.id]" type="number" min="0" step="0.25"
                  placeholder="0.00"
                  class="w-20 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400 text-center" />
              </div>
              <div class="text-xs text-right w-16 shrink-0" :class="margenColor(costos[item.id] || 0, item.precio)">
                <p class="font-bold">{{ calcPct(costos[item.id] || 0, item.precio) }}%</p>
                <p class="opacity-70">margen</p>
              </div>
            </div>
          </template>

          <!-- Combos: desglose por ingredientes -->
          <template v-else>
            <div v-for="item in itemsPorCategoria('combos')" :key="item.id" class="px-5 py-4">
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                  <span class="text-xl">{{ item.emoji }}</span>
                  <span class="font-semibold text-gray-800">{{ item.nombre }}</span>
                  <span class="text-orange-500 font-bold text-sm">Q{{ item.precio }}</span>
                </div>
                <button @click="abrirDesglose(item)"
                  class="text-xs bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-700 px-3 py-1.5 rounded-full font-semibold transition">
                  🧮 Desglosar ingredientes
                </button>
              </div>

              <!-- Resumen del desglose si ya existe -->
              <div v-if="comboCostos[item.id]?.componentes?.length" class="ml-8 mt-1">
                <div class="flex items-center gap-3">
                  <div class="flex-1">
                    <p v-for="(comp, ci) in comboCostos[item.id].componentes" :key="ci"
                      class="text-xs text-gray-500">
                      {{ comp.cantidad }} {{ comp.unidad }} {{ comp.nombre }}
                      <span class="text-gray-400">→ Q{{ (comp.cantidad * comp.costo_unitario).toFixed(2) }}</span>
                    </p>
                  </div>
                  <div class="text-right shrink-0">
                    <p class="text-xs text-gray-500">Costo total</p>
                    <p class="font-bold text-red-500 text-sm">Q{{ comboCostos[item.id].total.toFixed(2) }}</p>
                    <p class="font-bold text-sm" :class="margenColor(comboCostos[item.id].total, item.precio)">
                      {{ calcPct(comboCostos[item.id].total, item.precio) }}% margen
                    </p>
                  </div>
                </div>
              </div>
              <div v-else class="ml-8 mt-1">
                <p class="text-xs text-gray-400 italic">Sin desglose — toca "Desglosar ingredientes" para definir el costo</p>
              </div>
            </div>
          </template>

        </div>
      </div>

      <p v-if="guardadoCostos" class="text-green-600 text-sm text-center font-semibold mb-3">✓ Costos guardados</p>
      <button @click="guardarCostos" class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition">
        💾 Guardar costos
      </button>
    </div>

    <!-- MODAL: desglose de ingredientes de combo -->
    <div v-if="desgloseModal.visible" class="fixed inset-0 bg-black bg-opacity-60 flex items-end sm:items-center justify-center z-50 p-2 sm:p-4">
      <div class="bg-white rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div>
            <p class="font-bold text-gray-800 text-lg">{{ desgloseModal.item?.emoji }} {{ desgloseModal.item?.nombre }}</p>
            <p class="text-xs text-gray-400 mt-0.5">Precio de venta: <span class="font-bold text-orange-500">Q{{ desgloseModal.item?.precio }}</span></p>
          </div>
          <button @click="desgloseModal.visible = false" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">✕</button>
        </div>

        <!-- Tabla de ingredientes -->
        <div class="flex-1 overflow-y-auto px-5 py-4">
          <!-- Cabecera de columnas -->
          <div class="grid grid-cols-12 gap-2 mb-2 text-xs font-bold text-gray-500 uppercase tracking-wide">
            <span class="col-span-4">Ingrediente</span>
            <span class="col-span-2 text-center">Cant.</span>
            <span class="col-span-2 text-center">Unidad</span>
            <span class="col-span-2 text-center">Costo U.</span>
            <span class="col-span-1 text-right">Total</span>
            <span class="col-span-1"></span>
          </div>

          <div v-for="(comp, i) in desgloseModal.componentes" :key="i"
            class="grid grid-cols-12 gap-2 mb-2 items-center">
            <input v-model="comp.nombre" placeholder="Nombre" autocomplete="off"
              class="col-span-4 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <input v-model.number="comp.cantidad" type="number" min="0" step="0.5" placeholder="1"
              class="col-span-2 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <input v-model="comp.unidad" placeholder="u / lb"
              class="col-span-2 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <input v-model.number="comp.costo_unitario" type="number" min="0" step="0.25" placeholder="0.00"
              class="col-span-2 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <span class="col-span-1 text-right text-xs font-semibold text-gray-600">
              Q{{ ((comp.cantidad || 0) * (comp.costo_unitario || 0)).toFixed(2) }}
            </span>
            <button @click="desgloseModal.componentes.splice(i, 1)"
              class="col-span-1 text-red-400 hover:text-red-600 text-lg text-center leading-none">✕</button>
          </div>

          <button @click="agregarComponente"
            class="mt-3 w-full border border-dashed border-gray-300 text-gray-500 hover:border-orange-400 hover:text-orange-500 py-2 rounded-xl text-sm font-medium transition">
            + Agregar ingrediente
          </button>

          <!-- Resumen financiero del combo -->
          <div v-if="desgloseModal.componentes.length" class="mt-5 bg-gray-50 rounded-xl p-4">
            <div class="flex justify-between text-sm text-gray-600 mb-1">
              <span>Costo total ingredientes:</span>
              <span class="font-bold text-red-500">Q{{ desgloseTotal.toFixed(2) }}</span>
            </div>
            <div class="flex justify-between text-sm text-gray-600 mb-1">
              <span>Precio de venta:</span>
              <span class="font-bold text-orange-500">Q{{ desgloseModal.item?.precio || 0 }}</span>
            </div>
            <hr class="my-2 border-gray-200" />
            <div class="flex justify-between text-base font-bold">
              <span>Ganancia bruta:</span>
              <span :class="desgloseGanancia >= 0 ? 'text-green-600' : 'text-red-600'">
                Q{{ desgloseGanancia.toFixed(2) }}
              </span>
            </div>
            <div class="mt-2">
              <div class="flex justify-between text-xs mb-1">
                <span class="text-gray-500">Margen</span>
                <span class="font-bold" :class="margenColor(desgloseTotal, desgloseModal.item?.precio)">
                  {{ calcPct(desgloseTotal, desgloseModal.item?.precio) }}%
                </span>
              </div>
              <div class="h-3 bg-gray-200 rounded-full overflow-hidden">
                <div class="h-full rounded-full transition-all"
                  :class="calcPct(desgloseTotal, desgloseModal.item?.precio) >= 50 ? 'bg-green-500' : calcPct(desgloseTotal, desgloseModal.item?.precio) >= 30 ? 'bg-yellow-400' : 'bg-red-400'"
                  :style="{ width: Math.max(0, Math.min(100, calcPct(desgloseTotal, desgloseModal.item?.precio))) + '%' }"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Acciones -->
        <div class="flex gap-3 px-5 py-4 border-t border-gray-200 shrink-0">
          <button @click="desgloseModal.visible = false"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">
            Cancelar
          </button>
          <button @click="guardarDesglose"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl">
            💾 Guardar desglose
          </button>
        </div>
      </div>
    </div>

    <!-- ═══ PESTAÑA: INICIATIVAS ═══ -->
    <div v-if="tab === 'iniciativas'">
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-500">Ofertas especiales, descuentos o paquetes temporales</p>
        <button @click="abrirNuevaIniciativa"
          class="text-sm bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-xl font-semibold transition">
          + Nueva
        </button>
      </div>

      <div v-if="iniciativas.length === 0" class="text-center py-12 text-gray-400">
        <p class="text-4xl mb-3">🎯</p>
        <p class="font-medium">Sin iniciativas aún</p>
        <p class="text-sm mt-1">Crea ofertas como "Martes 2x1 Costilla" o "Combo Weekend"</p>
      </div>

      <div v-for="ini in iniciativas" :key="ini.id" class="bg-white border border-gray-200 rounded-2xl p-4 mb-3 shadow-sm">
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="text-xl">{{ ini.emoji }}</span>
              <span class="font-bold text-gray-800">{{ ini.nombre }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full" :class="ini.activa ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'">
                {{ ini.activa ? 'Activa' : 'Inactiva' }}
              </span>
            </div>
            <p class="text-sm text-gray-500 mt-1 ml-8">{{ ini.descripcion }}</p>
            <p class="text-orange-500 font-bold ml-8 mt-1">Q{{ ini.precio }}</p>
          </div>
          <div class="flex gap-2 shrink-0">
            <button @click="ini.activa = !ini.activa"
              class="text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition">
              {{ ini.activa ? 'Desactivar' : 'Activar' }}
            </button>
            <button @click="eliminarIniciativa(ini.id)" class="text-red-400 hover:text-red-600 px-2">✕</button>
          </div>
        </div>
      </div>

      <p v-if="guardadoIni" class="text-green-600 text-sm text-center font-semibold mb-3">✓ Iniciativas guardadas</p>
      <button v-if="iniciativas.length > 0" @click="guardarIniciativas"
        class="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-xl transition">
        💾 Guardar iniciativas
      </button>
    </div>

    <!-- MODAL: nuevo producto -->
    <div v-if="nuevoModal.visible" class="fixed inset-0 bg-black bg-opacity-50 flex items-end sm:items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl w-full max-w-md p-6 shadow-2xl">
        <h3 class="font-bold text-gray-800 mb-4">Nuevo producto — {{ catLabel(nuevoModal.categoria) }}</h3>
        <div class="space-y-3">
          <div class="flex gap-2">
            <div>
              <label class="text-xs text-gray-500 block mb-1">Emoji</label>
              <input v-model="nuevoModal.emoji" maxlength="4"
                class="w-14 border border-gray-200 rounded-lg px-2 py-2 text-xl text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div class="flex-1">
              <label class="text-xs text-gray-500 block mb-1">Nombre *</label>
              <input v-model="nuevoModal.nombre" autocomplete="off"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>
          <div class="flex gap-2">
            <div class="flex-1">
              <label class="text-xs text-gray-500 block mb-1">Precio (Q) *</label>
              <input v-model.number="nuevoModal.precio" type="number" min="0"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
            <div class="flex-1">
              <label class="text-xs text-gray-500 block mb-1">Unidad</label>
              <input v-model="nuevoModal.unidad" placeholder="pieza / lb / porción"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
            </div>
          </div>
          <div v-if="nuevoModal.categoria === 'combos'">
            <label class="text-xs text-gray-500 block mb-1">Contenido del combo</label>
            <input v-model="nuevoModal.contenido"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>
        </div>
        <p v-if="nuevoModal.error" class="text-red-500 text-xs mt-2">{{ nuevoModal.error }}</p>
        <div class="flex gap-3 mt-5">
          <button @click="nuevoModal.visible = false"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">Cancelar</button>
          <button @click="confirmarNuevo"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl">Agregar</button>
        </div>
      </div>
    </div>

    <!-- MODAL: nueva iniciativa -->
    <div v-if="iniModal.visible" class="fixed inset-0 bg-black bg-opacity-50 flex items-end sm:items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl w-full max-w-md p-6 shadow-2xl">
        <h3 class="font-bold text-gray-800 mb-4">Nueva iniciativa</h3>
        <div class="space-y-3">
          <div class="flex gap-2">
            <input v-model="iniModal.emoji" maxlength="4" placeholder="🎯"
              class="w-14 border border-gray-200 rounded-lg px-2 py-2 text-xl text-center focus:outline-none focus:ring-1 focus:ring-orange-400" />
            <input v-model="iniModal.nombre" placeholder="Nombre de la oferta" autocomplete="off"
              class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Descripción</label>
            <input v-model="iniModal.descripcion" placeholder="Ej: Martes de costilla 2x1" autocomplete="off"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Precio especial (Q)</label>
            <input v-model.number="iniModal.precio" type="number" min="0"
              class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-orange-400" />
          </div>
        </div>
        <div class="flex gap-3 mt-5">
          <button @click="iniModal.visible = false"
            class="flex-1 border border-gray-300 text-gray-600 font-semibold py-2.5 rounded-xl hover:bg-gray-50">Cancelar</button>
          <button @click="confirmarIniciativa"
            class="flex-1 bg-orange-500 hover:bg-orange-600 text-white font-bold py-2.5 rounded-xl">Crear</button>
        </div>
      </div>
    </div>

    <!-- MODAL: emoji picker -->
    <div v-if="emojiModal.visible" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-2xl w-80 p-5 shadow-2xl">
        <h3 class="font-bold text-gray-800 mb-3">Cambiar emoji</h3>
        <div class="grid grid-cols-6 gap-2 mb-4">
          <button v-for="e in emojiOpciones" :key="e" @click="seleccionarEmoji(e)"
            class="text-2xl p-2 rounded-xl hover:bg-orange-50 hover:scale-110 transition-transform">{{ e }}</button>
        </div>
        <input v-model="emojiModal.custom" maxlength="4" placeholder="O escribe aquí..."
          class="w-full border border-gray-200 rounded-lg px-3 py-2 text-center text-xl mb-3 focus:outline-none focus:ring-1 focus:ring-orange-400" />
        <div class="flex gap-2">
          <button @click="emojiModal.visible = false"
            class="flex-1 border border-gray-200 text-gray-500 py-2 rounded-xl text-sm hover:bg-gray-50">Cancelar</button>
          <button @click="aplicarEmojiCustom" :disabled="!emojiModal.custom"
            class="flex-1 bg-orange-500 text-white py-2 rounded-xl text-sm font-bold disabled:opacity-40">Aplicar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { getMenu, saveMenu, MENU_ITEMS, getCategorias, saveCategorias, CATEGORIAS } from '@/data/menu.js'

const tabs = [
  { key: 'menu',        label: '🍗 Menú' },
  { key: 'costos',      label: '💰 Costos' },
  { key: 'iniciativas', label: '🎯 Iniciativas' },
]
const tab = ref('menu')

// ─── MENÚ ───
const menu = reactive(JSON.parse(JSON.stringify(getMenu())))
const guardadoMenu = ref(false)

// Carga categorías desde localStorage (incluye las creadas por el usuario)
const categorias = reactive(JSON.parse(JSON.stringify(getCategorias())))

const nuevaCat = reactive({ key: '', label: '', emoji: '' })

function itemsPorCategoria(cat) { return menu.filter(i => i.categoria === cat) }
function catLabel(key) { return categorias.find(c => c.key === key)?.label || key }

function eliminarItem(id) {
  if (!confirm('¿Eliminar este producto?')) return
  const idx = menu.findIndex(i => i.id === id)
  if (idx !== -1) menu.splice(idx, 1)
}

function agregarCategoria() {
  const key = nuevaCat.key.trim().toLowerCase().replace(/\s+/g, '_')
  const label = nuevaCat.label.trim()
  if (!key || !label || categorias.find(c => c.key === key)) return
  categorias.push({ key, label, emoji: nuevaCat.emoji || '📦' })
  // Guardar inmediatamente para que persista
  saveCategorias([...categorias])
  nuevaCat.key = ''
  nuevaCat.label = ''
  nuevaCat.emoji = ''
}

function guardarMenu() {
  saveMenu(menu)
  saveCategorias([...categorias])
  guardadoMenu.value = true
  setTimeout(() => guardadoMenu.value = false, 2500)
}

function resetearMenu() {
  if (!confirm('¿Restaurar el menú original? Se borrarán las categorías personalizadas.')) return
  menu.splice(0, menu.length, ...JSON.parse(JSON.stringify(MENU_ITEMS)))
  categorias.splice(0, categorias.length, ...JSON.parse(JSON.stringify(getCategorias())))
  localStorage.removeItem('foodops_menu')
  localStorage.removeItem('foodops_categorias')
}

// ─── COSTOS (items simples) ───
function loadCostos() {
  try { return JSON.parse(localStorage.getItem('foodops_costos') || '{}') } catch { return {} }
}
const costos = reactive(loadCostos())
const guardadoCostos = ref(false)

// ─── COSTOS COMBO (desglose por ingrediente) ───
function loadComboCostos() {
  try { return JSON.parse(localStorage.getItem('foodops_combo_costos') || '{}') } catch { return {} }
}
const comboCostos = reactive(loadComboCostos())

// Helpers de margen (reciben costo y precio como números)
function calcPct(costo, precio) {
  if (!precio || !costo) return 0
  return Math.round(((precio - costo) / precio) * 100)
}
function margenColor(costo, precio) {
  const pct = calcPct(costo, precio)
  if (!pct) return 'text-gray-300'
  if (pct >= 50) return 'text-green-600'
  if (pct >= 30) return 'text-yellow-500'
  return 'text-red-500'
}

// ─── MODAL DESGLOSE DE COMBO ───
const desgloseModal = reactive({
  visible: false,
  item: null,
  componentes: [],
})

const desgloseTotal = computed(() =>
  desgloseModal.componentes.reduce((s, c) => s + (c.cantidad || 0) * (c.costo_unitario || 0), 0)
)
const desgloseGanancia = computed(() =>
  (desgloseModal.item?.precio || 0) - desgloseTotal.value
)

function abrirDesglose(item) {
  // Cargar componentes guardados o inicializar vacío
  const guardado = comboCostos[item.id]
  desgloseModal.item = item
  desgloseModal.componentes = guardado?.componentes
    ? JSON.parse(JSON.stringify(guardado.componentes))
    : []
  desgloseModal.visible = true
}

function agregarComponente() {
  desgloseModal.componentes.push({ nombre: '', cantidad: 1, unidad: 'u', costo_unitario: 0 })
}

function guardarDesglose() {
  const id = desgloseModal.item.id
  const componentes = desgloseModal.componentes.filter(c => c.nombre.trim())
  comboCostos[id] = {
    componentes,
    total: componentes.reduce((s, c) => s + (c.cantidad || 0) * (c.costo_unitario || 0), 0),
  }
  localStorage.setItem('foodops_combo_costos', JSON.stringify({ ...comboCostos }))
  desgloseModal.visible = false
}

function guardarCostos() {
  localStorage.setItem('foodops_costos', JSON.stringify({ ...costos }))
  localStorage.setItem('foodops_combo_costos', JSON.stringify({ ...comboCostos }))
  guardadoCostos.value = true
  setTimeout(() => guardadoCostos.value = false, 2500)
}

// ─── INICIATIVAS ───
function loadIniciativas() {
  try { return JSON.parse(localStorage.getItem('foodops_iniciativas') || '[]') } catch { return [] }
}
const iniciativas = reactive(loadIniciativas())
const guardadoIni = ref(false)

const iniModal = reactive({ visible: false, emoji: '🎯', nombre: '', descripcion: '', precio: '' })

function abrirNuevaIniciativa() {
  Object.assign(iniModal, { visible: true, emoji: '🎯', nombre: '', descripcion: '', precio: '' })
}

function confirmarIniciativa() {
  if (!iniModal.nombre.trim()) return
  const maxId = iniciativas.reduce((m, i) => Math.max(m, i.id || 0), 0)
  iniciativas.push({
    id: maxId + 1,
    emoji: iniModal.emoji || '🎯',
    nombre: iniModal.nombre.trim(),
    descripcion: iniModal.descripcion.trim(),
    precio: Number(iniModal.precio) || 0,
    activa: true,
  })
  iniModal.visible = false
  guardarIniciativas()
}

function eliminarIniciativa(id) {
  const idx = iniciativas.findIndex(i => i.id === id)
  if (idx !== -1) iniciativas.splice(idx, 1)
  guardarIniciativas()
}

function guardarIniciativas() {
  localStorage.setItem('foodops_iniciativas', JSON.stringify([...iniciativas]))
  guardadoIni.value = true
  setTimeout(() => guardadoIni.value = false, 2500)
}

// ─── MODAL NUEVO PRODUCTO ───
const nuevoModal = reactive({
  visible: false, categoria: '', emoji: '', nombre: '',
  precio: '', unidad: 'porción', contenido: '', error: '',
})

function abrirNuevo(cat) {
  Object.assign(nuevoModal, { visible: true, categoria: cat, emoji: '', nombre: '', precio: '', unidad: 'porción', contenido: '', error: '' })
}

function confirmarNuevo() {
  nuevoModal.error = ''
  if (!nuevoModal.nombre.trim()) { nuevoModal.error = 'El nombre es requerido'; return }
  if (!nuevoModal.precio || Number(nuevoModal.precio) < 0) { nuevoModal.error = 'Ingresa un precio válido'; return }
  const maxId = menu.reduce((m, i) => Math.max(m, i.id || 0), 0)
  const nuevo = {
    id: maxId + 1,
    nombre: nuevoModal.nombre.trim(),
    precio: Number(nuevoModal.precio),
    categoria: nuevoModal.categoria,
    unidad: nuevoModal.unidad || 'porción',
    emoji: nuevoModal.emoji || '🍽️',
  }
  if (nuevoModal.categoria === 'combos' && nuevoModal.contenido) nuevo.contenido = nuevoModal.contenido.trim()
  menu.push(nuevo)
  nuevoModal.visible = false
}

// ─── EMOJI PICKER ───
const emojiOpciones = [
  '🍗','🥓','🥘','🔥','👑','🥔','🍚','🥗','🧀','🍝',
  '🌶️','🫑','🧅','🧄','🍋','🥤','🧃','🍺','🥛','☕',
  '🍕','🌮','🌯','🥙','🥚','🍳','🥞','🧇','🫔','🥣',
  '🍖','🫕','🥩','🥦','🫛','🌽','🫚','🫙','🥫','🍱',
  '➕','🎁','⭐','💎','🏆','🎯','🔑','🎪','🎠','🎡',
]
const emojiModal = reactive({ visible: false, item: null, custom: '' })

function cambiarEmoji(item) { emojiModal.item = item; emojiModal.custom = ''; emojiModal.visible = true }
function seleccionarEmoji(e) { if (emojiModal.item) emojiModal.item.emoji = e; emojiModal.visible = false }
function aplicarEmojiCustom() { if (emojiModal.item && emojiModal.custom) emojiModal.item.emoji = emojiModal.custom; emojiModal.visible = false }
</script>
