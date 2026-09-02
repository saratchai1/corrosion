const frame = document.querySelector('#frame')
const clip = document.querySelector('#clip')
const divider = document.querySelector('#divider')
const plane = document.querySelector('#plane')
const zoom = document.querySelector('#zoom')
const zoomValue = document.querySelector('#zoomValue')
const reset = document.querySelector('#reset')

let split = 50
let dragging = false

function drawSplit(value) {
  split = Math.max(3, Math.min(97, value))
  clip.style.clipPath = `inset(0 ${100 - split}% 0 0)`
  divider.style.left = `${split}%`
}

function updateFromPointer(clientX) {
  const rect = frame.getBoundingClientRect()
  drawSplit(((clientX - rect.left) / rect.width) * 100)
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

reset.addEventListener('click', () => {
  drawSplit(50)
  zoom.value = '1'
  plane.style.transform = 'scale(1)'
  zoomValue.textContent = '1.0×'
})

drawSplit(50)
