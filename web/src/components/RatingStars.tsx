import { useState } from 'react';
import { versionsApi } from '../api/versions';
import './RatingStars.css';

interface RatingStarsProps {
  versionId: string;
  initialRating: number | null;
  onRatingChange?: (newRating: number | null) => void;
  readOnly?: boolean;
}

export default function RatingStars({
  versionId,
  initialRating,
  onRatingChange,
  readOnly = false,
}: RatingStarsProps) {
  const [rating, setRating] = useState<number | null>(initialRating);
  const [isLoading, setIsLoading] = useState(false);
  const [hoverRating, setHoverRating] = useState<number | null>(null);

  const handleStarClick = async (value: number) => {
    if (readOnly || isLoading) return;

    setIsLoading(true);
    try {
      // Clicking the same star again clears the rating
      if (rating === value) {
        await versionsApi.clearRating(versionId);
        setRating(null);
        onRatingChange?.(null);
      } else {
        await versionsApi.setRating(versionId, value);
        setRating(value);
        onRatingChange?.(value);
      }
    } catch (error) {
      console.error('Failed to update rating:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const displayRating = hoverRating ?? rating;

  return (
    <div className="rating-stars" onMouseLeave={() => setHoverRating(null)}>
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          className={`star ${star <= (displayRating ?? 0) ? 'filled' : 'empty'}`}
          onClick={() => handleStarClick(star)}
          onMouseEnter={() => setHoverRating(star)}
          disabled={readOnly || isLoading}
          title={`Rate ${star}`}
          aria-label={`Rate ${star} stars`}
        >
          ★
        </button>
      ))}
      {rating && (
        <span className="rating-value">
          {rating}/5
        </span>
      )}
    </div>
  );
}
