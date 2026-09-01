import { access, cp, mkdir, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const appRoot = process.cwd()
const repoRoot = resolve(appRoot, '..')
const source = join(repoRoot, 'web', 'public', 'data', 'surat_thani')
const boundarySource = join(repoRoot, 'data', 'aoi', 'surat_thani_37_stc_current_aoi.geojson')
const target = join(appRoot, 'public', 'data', 'surat_thani')
const targetIndex = join(target, 'index.json')
const boundaryTarget = join(target, 'project_boundary.geojson')

async function exists(path) {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

if (await exists(source)) {
  await rm(target, { recursive: true, force: true })
  await mkdir(target, { recursive: true })
  await cp(source, target, { recursive: true })
  if (await exists(boundarySource)) {
    await cp(boundarySource, boundaryTarget)
  }
  console.log(`Synced current Surat Thani pipeline data -> ${target}`)
} else if (await exists(targetIndex)) {
  // The main branch carries a self-contained snapshot so Vercel can create the
  // standalone project without touching the existing Samut Songkhram web root.
  console.log(`Using bundled Surat Thani snapshot -> ${target}`)
} else {
  throw new Error(`Surat Thani data unavailable: missing both ${source} and ${targetIndex}`)
}
