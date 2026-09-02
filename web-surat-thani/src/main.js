const frame = document.querySelector('#frame')
const clip = document.querySelector('#clip')
const divider = document.querySelector('#divider')
const plane = document.querySelector('#plane')
const zoom = document.querySelector('#zoom')
const zoomValue = document.querySelector('#zoomValue')
const reset = document.querySelector('#reset')
const plotPicker = document.querySelector('#plotPicker')
const currentMeta = document.querySelector('#currentMeta')
const baseImage = document.querySelector('#baseImage')
const detailImage = document.querySelector('#detailImage')

let split = 50
let dragging = false
let locations = []
let activeId = '91-stc'

function drawSplit(value) {
  split = Math.max(3, Math.min(97, value))
  clip.style.clipPath = `inset(0 ${100 - split}% 0 0)`
  divider.style.left = `${split}%`
}

function updateFromPointer(clientX) {
  const rect = frame.getBoundingClientRect()
  drawSplit(((clientX - rect.left) / rect.width) * 100)
}

function resetView() {
  drawSplit(50)
  zoom.value = '1'
  plane.style.transform = 'scale(1)'
  zoomValue.textContent = '1.0×'
}

function assetUrl(path) {
  return `/${String(path).replace(/^\/+/, '')}`
}

function preload(url) {
  const image = new Image()
  image.src = url
}

function selectLocation(location) {
  if (!location) return
  activeId = location.id
  const original = assetUrl(location.original)
  const refined = assetUrl(location.superres)
  preload(original)
  preload(refined)
  baseImage.src = original
  detailImage.src = refined
  currentMeta.textContent = `${location.label} · 15 ม.ค. 2025`
  for (const button of plotPicker.querySelectorAll('button')) {
    const active = button.dataset.id === activeId
    button.classList.toggle('active', active)
    button.setAttribute('aria-pressed', String(active))
  }
  resetView()
}

function renderPicker() {
  plotPicker.replaceChildren()
  for (const location of locations) {
    const button = document.createElement('button')
    button.type = 'button'
    button.dataset.id = location.id
    button.textContent = location.label
    button.setAttribute('aria-pressed', 'false')
    button.addEventListener('click', () => selectLocation(location))
    plotPicker.appendChild(button)
  }
  selectLocation(locations.find((item) => item.id === activeId) || locations[0])
}

async function loadLocations() {
  try {
    const response = await fetch(`/data/superres25/summary.json?v=${Date.now()}`, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const summary = await response.json()
    locations = Array.isArray(summary.locations) ? summary.locations : []
    if (locations.length) renderPicker()
  } catch (error) {
    console.error('Could not load plot list', error)
  }
}

frame.addEventListener('pointerdown', (event) => {
  dragging = true
  frame.setPointerCapture(event.pointerId)
  updateFromPointer(event.clientX)
})

frame.addEventListener('pointermove', (event) => {
  if (dragging) updateFromPointer(event.clientX)
})

frame.addEventListener('pointerup', (event) => {
  dragging = false
  if (frame.hasPointerCapture(event.pointerId)) frame.releasePointerCapture(event.pointerId)
})

frame.addEventListener('pointercancel', () => { dragging = false })

zoom.addEventListener('input', () => {
  const value = Number(zoom.value)
  plane.style.transform = `scale(${value})`
  zoomValue.textContent = `${value.toFixed(1)}×`
})

reset.addEventListener('click', resetView)

drawSplit(50)
loadLocations()
