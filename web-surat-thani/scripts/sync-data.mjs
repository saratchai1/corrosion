import { cp, mkdir, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const appRoot = process.cwd()
const repoRoot = resolve(appRoot, '..')
const source = join(repoRoot, 'web', 'public', 'data', 'surat_thani')
const target = join(appRoot, 'public', 'data', 'surat_thani')

await rm(target, { recursive: true, force: true })
await mkdir(target, { recursive: true })
await cp(source, target, { recursive: true })
await cp(
  join(repoRoot, 'data', 'aoi', 'surat_thani_37_stc_current_aoi.geojson'),
  join(target, 'project_boundary.geojson'),
)
console.log(`Synced Surat Thani static data -> ${target}`)
