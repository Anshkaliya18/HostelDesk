import { useEffect, useRef, useState } from 'react'
import PhotoUpload from './PhotoUpload.jsx'
import { AlertIcon } from './Icons.jsx'
import { preparePhoto, validatePhotoFile } from '../utils/image.js'
import { submitComplaint } from '../services/complaints.js'

const DESCRIPTION_MAX_LENGTH = 1000
// Mirror the FastAPI Form() limits exactly, so the client can never build a
// request the server is bound to reject with 422.
const BLOCK_MAX_LENGTH = 40
const ROOM_MAX_LENGTH = 60

function validateField(field, value) {
  if (field === 'description') {
    return value.trim() ? '' : "Please describe what's wrong."
  }

  if (field === 'block') {
    return value.trim() ? '' : 'Add the block letter.'
  }

  if (field === 'room') {
    return value.trim() ? '' : 'Add the room number.'
  }

  return ''
}

export default function ComplaintForm({ onSuccess, accessToken, autoFocusDescription = false }) {
  const [description, setDescription] = useState('')
  const [block, setBlock] = useState('')
  const [room, setRoom] = useState('')
  const [photo, setPhoto] = useState(null)
  const [photoError, setPhotoError] = useState('')
  const [isPhotoProcessing, setIsPhotoProcessing] = useState(false)
  const [errors, setErrors] = useState({})
  const [submitError, setSubmitError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const submittingRef = useRef(false)
  const photoUrlRef = useRef(null)
  const descriptionRef = useRef(null)
  const blockRef = useRef(null)
  const roomRef = useRef(null)

  useEffect(() => {
    return () => {
      if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current)
    }
  }, [])

  useEffect(() => {
    if (autoFocusDescription) descriptionRef.current?.focus()
  }, [autoFocusDescription])

  function replacePhoto(file) {
    const nextPreviewUrl = file ? URL.createObjectURL(file) : null

    if (photoUrlRef.current) URL.revokeObjectURL(photoUrlRef.current)
    photoUrlRef.current = nextPreviewUrl

    setPhoto(
      file
        ? {
            file,
            previewUrl: nextPreviewUrl,
            name: file.name,
            size: file.size,
          }
        : null,
    )
  }

  function handleDescriptionChange(event) {
    setDescription(event.target.value)
    setErrors((current) =>
      current.description ? { ...current, description: '' } : current,
    )
  }

  function handleBlockChange(event) {
    setBlock(event.target.value)
    setErrors((current) => (current.block ? { ...current, block: '' } : current))
  }

  function handleRoomChange(event) {
    setRoom(event.target.value)
    setErrors((current) => (current.room ? { ...current, room: '' } : current))
  }

  function handleBlur(field) {
    if (field === 'description') return handleBlurValue(field, description)
    if (field === 'block') return handleBlurValue(field, block)
    return handleBlurValue(field, room)
  }

  function handleBlurValue(field, value) {
    const message = validateField(field, value)

    setErrors((current) => {
      if ((current[field] ?? '') === message) return current
      return { ...current, [field]: message }
    })
  }

  async function handlePhotoSelect(file) {
    setPhotoError('')
    const validationError = validatePhotoFile(file)

    if (validationError) {
      setPhotoError(validationError)
      return false
    }

    setIsPhotoProcessing(true)

    try {
      const preparedFile = await preparePhoto(file)
      replacePhoto(preparedFile)
      return true
    } catch (error) {
      console.error('Photo preparation failed:', error)
      setPhotoError("We couldn't prepare that photo. Try a different image.")
      return false
    } finally {
      setIsPhotoProcessing(false)
    }
  }

  function handlePhotoRemove() {
    replacePhoto(null)
    setPhotoError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submittingRef.current || isPhotoProcessing) return

    setSubmitError('')

    const nextErrors = {
      description: validateField('description', description),
      block: validateField('block', block),
      room: validateField('room', room),
    }
    setErrors(nextErrors)

    if (nextErrors.description || nextErrors.block || nextErrors.room) {
      window.requestAnimationFrame(() => {
        if (nextErrors.description) {
          descriptionRef.current?.focus()
        } else if (nextErrors.block) {
          blockRef.current?.focus()
        } else {
          roomRef.current?.focus()
        }
      })
      return
    }

    submittingRef.current = true
    setIsSubmitting(true)

    try {
      const result = await submitComplaint({
        description: description.trim(),
        block: block.trim(),
        room: room.trim(),
        photo: photo?.file ?? null,
        accessToken,
      })

      onSuccess(result)
    } catch (error) {
      console.error('Complaint submission failed:', error)
      setSubmitError('Something went wrong. Please try again.')
      setIsSubmitting(false)
      submittingRef.current = false
    }
  }

  const descriptionDescribedBy = [
    'description-hint',
    errors.description ? 'description-error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  const blockDescribedBy = ['block-hint', errors.block ? 'block-error' : '']
    .filter(Boolean)
    .join(' ')

  const roomDescribedBy = ['room-hint', errors.room ? 'room-error' : '']
    .filter(Boolean)
    .join(' ')

  return (
    <form
      className="panel form-panel"
      noValidate
      aria-labelledby="complaint-details-title"
      aria-busy={isSubmitting}
      onSubmit={handleSubmit}
    >
      <div className="panel__header">
        <h2 className="panel__title" id="complaint-details-title">
          Complaint details
        </h2>
        <p className="panel__meta">
          Fields marked <span className="required-mark">*</span> are required
        </p>
      </div>

      <div className="form-panel__body">
        <fieldset className="form-fields" disabled={isSubmitting}>
          <div className="field">
            <label className="field__label" htmlFor="description">
              What&apos;s wrong?
              <span className="required-mark" aria-hidden="true">
                *
              </span>
            </label>
            <p className="field__hint" id="description-hint">
              Describe what is broken and how long it has been an issue.
            </p>
            <textarea
              ref={descriptionRef}
              className={`textarea${errors.description ? ' control--error' : ''}`}
              id="description"
              name="description"
              rows={5}
              maxLength={DESCRIPTION_MAX_LENGTH}
              placeholder="Example: The ceiling fan in room 204 is not working."
              value={description}
              required
              aria-invalid={Boolean(errors.description)}
              aria-describedby={descriptionDescribedBy}
              onChange={handleDescriptionChange}
              onBlur={() => handleBlur('description')}
            />
            {errors.description ? (
              <p className="field-error" id="description-error">
                <AlertIcon size={15} />
                <span>{errors.description}</span>
              </p>
            ) : null}
          </div>

          <div className="field-row">
            <div className="field">
              <label className="field__label" htmlFor="block">
                Block
                <span className="required-mark" aria-hidden="true">
                  *
                </span>
              </label>
              <p className="field__hint" id="block-hint">
                The block letter so we can route the complaint correctly.
              </p>
              <input
                ref={blockRef}
                className={`input${errors.block ? ' control--error' : ''}`}
                id="block"
                name="block"
                type="text"
                maxLength={BLOCK_MAX_LENGTH}
                placeholder="A"
                value={block}
                required
                autoComplete="off"
                list="block-suggestions"
                aria-invalid={Boolean(errors.block)}
                aria-describedby={blockDescribedBy}
                onChange={handleBlockChange}
                onBlur={() => handleBlur('block')}
              />
              <datalist id="block-suggestions">
                {['A', 'B', 'C', 'D', 'E', 'F'].map(letter => <option key={letter} value={letter} />)}
              </datalist>
              {errors.block ? (
                <p className="field-error" id="block-error">
                  <AlertIcon size={15} />
                  <span>{errors.block}</span>
                </p>
              ) : null}
            </div>

            <div className="field">
              <label className="field__label" htmlFor="room">
                Room
                <span className="required-mark" aria-hidden="true">
                  *
                </span>
              </label>
              <p className="field__hint" id="room-hint">
                The room number inside that block.
              </p>
              <input
                ref={roomRef}
                className={`input${errors.room ? ' control--error' : ''}`}
                id="room"
                name="room"
                type="text"
                maxLength={ROOM_MAX_LENGTH}
                placeholder="204"
                value={room}
                required
                autoComplete="off"
                aria-invalid={Boolean(errors.room)}
                aria-describedby={roomDescribedBy}
                onChange={handleRoomChange}
                onBlur={() => handleBlur('room')}
              />
              {errors.room ? (
                <p className="field-error" id="room-error">
                  <AlertIcon size={15} />
                  <span>{errors.room}</span>
                </p>
              ) : null}
            </div>
          </div>

          <PhotoUpload
            photo={photo}
            error={photoError}
            isProcessing={isPhotoProcessing}
            disabled={isSubmitting}
            onSelect={handlePhotoSelect}
            onRemove={handlePhotoRemove}
          />
        </fieldset>

        {submitError ? (
          <div className="form-alert" role="alert">
            <AlertIcon size={17} />
            <span>{submitError}</span>
          </div>
        ) : null}
      </div>

      <div className="form-panel__footer">
        <button
          type="submit"
          className="button button--primary"
          disabled={isSubmitting || isPhotoProcessing}
        >
          {isSubmitting ? <span className="spinner" aria-hidden="true" /> : null}
          {isSubmitting ? 'Submitting…' : 'Submit complaint'}
        </button>
        <span className="visually-hidden" role="status" aria-live="polite">
          {isSubmitting ? 'Submitting your complaint.' : ''}
        </span>
      </div>
    </form>
  )
}
