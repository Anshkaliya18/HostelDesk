const MAX_EDGE = 1600
const JPEG_QUALITY = 0.84
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp'])
const ALLOWED_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp'])

export const MAX_PHOTO_MB = 15
export const MAX_PHOTO_BYTES = MAX_PHOTO_MB * 1024 * 1024
export const PHOTO_ACCEPT = Array.from(ALLOWED_TYPES).join(',')
export const PHOTO_FORMAT_LABEL = 'JPG, PNG or WebP'

export function validatePhotoFile(file) {
  if (!file) return 'Choose a photo to upload.'

  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  const hasSupportedType = ALLOWED_TYPES.has(file.type)
  const hasSupportedExtension = ALLOWED_EXTENSIONS.has(extension)
  const typeIsUnknown = !file.type

  if (!hasSupportedType && !(typeIsUnknown && hasSupportedExtension)) {
    return `Choose a ${PHOTO_FORMAT_LABEL} photo.`
  }

  if (file.size === 0) {
    return 'That file is empty. Try another photo.'
  }

  if (file.size > MAX_PHOTO_BYTES) {
    return `That photo is too large. Choose an image under ${MAX_PHOTO_MB} MB.`
  }

  return ''
}

export function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'

  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.decoding = 'async'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('The selected image could not be read.'))
    image.src = src
  })
}

function canvasToBlob(canvas) {
  return new Promise((resolve) => {
    canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
  })
}

/**
 * Resizes a photo and re-encodes it as JPEG. Re-encoding also removes
 * camera metadata (including location data) before the file is uploaded.
 */
export async function preparePhoto(file) {
  const sourceUrl = URL.createObjectURL(file)

  try {
    const image = await loadImage(sourceUrl)
    const sourceWidth = image.naturalWidth
    const sourceHeight = image.naturalHeight

    if (!sourceWidth || !sourceHeight) {
      throw new Error('The selected image has no usable dimensions.')
    }

    const scale = Math.min(1, MAX_EDGE / Math.max(sourceWidth, sourceHeight))
    const width = Math.max(1, Math.round(sourceWidth * scale))
    const height = Math.max(1, Math.round(sourceHeight * scale))

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height

    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('A canvas context could not be created.')
    }

    // JPEG has no transparency, so transparent PNGs need a neutral background.
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, width, height)
    context.imageSmoothingEnabled = true
    context.imageSmoothingQuality = 'high'
    context.drawImage(image, 0, 0, width, height)

    const blob = await canvasToBlob(canvas)
    if (!blob) {
      throw new Error('The selected image could not be encoded.')
    }

    const baseName =
      file.name
        .replace(/\.[^./\\]+$/, '')
        .replace(/[^\w -]/g, '')
        .trim()
        .slice(0, 80) || 'complaint-photo'

    return new File([blob], `${baseName}.jpg`, {
      type: 'image/jpeg',
      lastModified: Date.now(),
    })
  } finally {
    URL.revokeObjectURL(sourceUrl)
  }
}
