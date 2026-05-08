import { useState } from 'react';
type RunRating = { rating: number | null };
const runRatingsApi = {
  setRating: async (runId: string, value: number): Promise<RunRating> => {
    const r = await fetch(`/api/runs/${encodeURIComponent(runId)}/rating`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ rating: value }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  clearRating: async (runId: string): Promise<void> => {
    const r = await fetch(`/api/runs/${encodeURIComponent(runId)}/rating`, { method: 'DELETE' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  },
};
import './RatingStars.css';

interface RunRatingStarsProps {
  runId: string;
  initialRating: number | null;
  onRatingChange?: (newRating: number | null) => void;
  readOnly?: boolean;
}

export default function RunRatingStars({
  runId,
  initialRating,
  onRatingChange,
  readOnly = false,
}: RunRatingStarsProps) {
  const [rating, setRating] = useState<number | null>(initialRating);
  const [isLoading, setIsLoading] = useState(false);
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleStarClick = async (value: number) => {
    if (readOnly || isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      if (rating === value) {
        await runRatingsApi.clearRating(runId);
        setRating(null);
        onRatingChange?.(null);
      } else {
        const result: RunRating = await runRatingsApi.setRating(runId, value);
        setRating(result.rating);
        onRatingChange?.(result.rating);
      }
    } catch (err) {
      console.error('Failed to update run rating:', err);
      setError('Failed to update rating');
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
          title={`Rate ${star} stars`}
          aria-label={`Rate ${star} stars`}
        >
          ★
        </button>
      ))}
      {rating && <span className="rating-value">{rating}/5</span>}
      {error && <span className="rating-error" title={error}>!</span>}
    </div>
  );
}
