import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiPost } from "@/lib/api";
import { extractErrorMessage } from "@/lib/format";
import type { Review, ReviewCreate } from "@/lib/types";

/** Star rating + comment. With an exchangeId the review is verified; without one it is labelled unverified. */
export default function ReviewForm({
  subjectId,
  subjectName,
  exchangeId,
  testId,
  onDone,
}: {
  subjectId: string;
  subjectName: string;
  exchangeId?: string;
  testId: string;
  onDone?: () => void;
}) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");

  const submit = useMutation({
    mutationFn: (payload: ReviewCreate) => apiPost<Review>(`/v1/users/${subjectId}/reviews`, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["reputation", subjectId] });
      toast.success(`Review for ${subjectName} posted`);
      setRating(0);
      setComment("");
      onDone?.();
    },
    onError: (error) => toast.error(extractErrorMessage(error, "Could not post this review")),
  });

  return (
    <form
      className="space-y-3"
      data-testid={testId}
      onSubmit={(event) => {
        event.preventDefault();
        if (!rating) {
          toast.error("Pick a star rating first");
          return;
        }
        submit.mutate({ rating, comment, exchange_id: exchangeId ?? null });
      }}
    >
      <div className="flex items-center gap-1" role="radiogroup" aria-label={`Rate ${subjectName}`}>
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={rating === value}
            onClick={() => setRating(value)}
            className="rounded p-0.5 transition-transform duration-150 hover:scale-110"
            data-testid={`${testId}-star-${value}`}
          >
            <Star
              className={`size-5 transition-colors duration-150 ${value <= rating ? "fill-amber-300 text-amber-500" : "text-slate-400"}`}
              aria-hidden
            />
          </button>
        ))}
        <span className="ml-2 text-xs text-slate-500">
          {exchangeId ? "Verified trade review" : "Unverified review (doesn't count toward the rating)"}
        </span>
      </div>
      <Textarea
        value={comment}
        maxLength={1000}
        placeholder={`How was trading with ${subjectName}?`}
        onChange={(event) => setComment(event.target.value)}
        data-testid={`${testId}-comment-input`}
      />
      <Button type="submit" size="sm" disabled={submit.isPending} data-testid={`${testId}-submit-button`}>
        {submit.isPending ? "Posting…" : "Post review"}
      </Button>
    </form>
  );
}
