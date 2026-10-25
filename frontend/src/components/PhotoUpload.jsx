import { useEffect, useRef, useState } from 'react'
import { AlertIcon, ImageIcon } from './Icons.jsx'
import {
  MAX_PHOTO_MB,
  PHOTO_ACCEPT,
  PHOTO_FORMAT_LABEL,
  formatFileSize,
} from '../utils/image.js'

export default function PhotoUpload({
  photo,
  error,
  isProcessing,
  disabled = false,
  onSelect,
  onRemove,
}) {
  const inputRef = useRef(null)
  const uploadButtonRef = useRef(null)
  const changeButtonRef = useRef(null)
  const dragDepth = useRef(0)
  const focusTarget = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const [announcement, setAnnouncement] = useState('')

  const describedBy = ['photo-hint', error ? 'photo-error' : ''].filter(Boolean).join(' ')

  useEffect(() => {
    if (focusTarget.current === 'change' && photo) {
      focusTarget.current = null
      changeButtonRef.current?.focus()
    }

    if (focusTarget.current === 'upload' && !photo) {
      focusTarget.current = null
      uploadButtonRef.current?.focus()
    }
  }, [photo])

  async function handleFile(file) {
    if (!file || disabled || isProcessing) return

    // Move focus into the new preview once the file has been processed.
    focusTarget.current = 'change'
    setAnnouncement('Preparing photo…')
    const added = await onSelect(file)

    if (added) {
      setAnnouncement(`Photo selected: ${file.name}`)
    }
  }

  function handleInputChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) handleFile(file)
  }

  function handleDragEnter(event) {
    event.preventDefault()
    if (disabled || isProcessing) return
    dragDepth.current += 1
    setIsDragging(true)
  }

  function handleDragOver(event) {
    event.preventDefault()
    if (!disabled && !isProcessing) event.dataTransfer.dropEffect = 'copy'
  }

  function handleDragLeave(event) {
    event.preventDefault()
    if (disabled || isProcessing) return
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setIsDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    dragDepth.current = 0
    setIsDragging(false)
    if (disabled || isProcessing) return

    const file = event.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  function handleRemove() {
    focusTarget.current = 'upload'
    setAnnouncement('Photo removed.')
    onRemove()
  }

  return (
    <div
      className="field photo-field"
      role="group"
      aria-labelledby="photo-label photo-optional"
      aria-busy={isProcessing || undefined}
    >
      <div className="photo-field__label-row">
        <span className="field__label" id="photo-label">
          Photo
        </span>
        <span className="optional-label" id="photo-optional">
          Optional
        </span>
      </div>
      <p className="field__hint" id="photo-hint">
        A photo can help the maintenance team understand the issue.
      </p>

      <input
        ref={inputRef}
        className="visually-hidden"
        id="complaint-photo"
        type="file"
        accept={PHOTO_ACCEPT}
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled || isProcessing}
        onChange={handleInputChange}
      />

      {isProcessing ? (
        <div className="upload-processing" role="status">
          <span className="spinner" aria-hidden="true" />
          <div>
            <p className="upload-processing__title">Preparing photo…</p>
            <p className="upload-processing__hint">
              Resizing the image so your complaint sends quickly.
            </p>
          </div>
        </div>
      ) : photo ? (
        <div className="photo-preview">
          <div className="photo-preview__thumb">
            <img src={photo.previewUrl} alt="" decoding="async" />
          </div>
          <div className="photo-preview__details">
            <p className="photo-preview__name" title={photo.name}>
              {photo.name}
            </p>
            <p className="photo-preview__meta">{formatFileSize(photo.size)} · Ready to attach</p>
            <div className="photo-preview__actions">
              <button
                ref={changeButtonRef}
                type="button"
                className="text-button"
                disabled={disabled}
                onClick={() => inputRef.current?.click()}
              >
                Change photo
              </button>
              <span className="action-divider" aria-hidden="true" />
              <button
                type="button"
                className="text-button text-button--danger"
                disabled={disabled}
                onClick={handleRemove}
              >
                Remove
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          ref={uploadButtonRef}
          type="button"
          className={`upload-zone${isDragging ? ' upload-zone--dragging' : ''}${
            error ? ' upload-zone--error' : ''
          }`}
          disabled={disabled}
          aria-describedby={describedBy}
          aria-invalid={Boolean(error)}
          onClick={() => inputRef.current?.click()}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <span className="upload-zone__icon" aria-hidden="true">
            <ImageIcon size={21} />
          </span>
          <span className="upload-zone__text">
            <span className="upload-zone__title">Upload a photo</span>
            <span className="upload-zone__hint">Choose a file or drag and drop</span>
            <span className="upload-zone__meta">
              {PHOTO_FORMAT_LABEL} · up to {MAX_PHOTO_MB} MB
            </span>
          </span>
        </button>
      )}

      {error ? (
        <p className="field-error" id="photo-error" role="alert">
          <AlertIcon size={15} />
          <span>{error}</span>
        </p>
      ) : null}

      <span className="visually-hidden" role="status" aria-live="polite">
        {announcement}
      </span>
    </div>
  )
}
