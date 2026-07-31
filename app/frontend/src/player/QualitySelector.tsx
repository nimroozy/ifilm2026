import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { QualityLevel } from './types';

export function QualitySelector({
  levels,
  currentLevel,
  onChange,
  disabled,
  unsupportedReason,
}: {
  levels: QualityLevel[];
  currentLevel: number;
  onChange: (level: number) => void;
  disabled?: boolean;
  unsupportedReason?: string | null;
}) {
  if (unsupportedReason) {
    return (
      <p className="text-xs text-white/60" data-testid="quality-unavailable">
        {unsupportedReason}
      </p>
    );
  }
  if (!levels.length) return null;

  const value = currentLevel === -1 ? 'auto' : String(currentLevel);

  return (
    <Select
      value={value}
      onValueChange={(v) => onChange(v === 'auto' ? -1 : Number(v))}
      disabled={disabled}
    >
      <SelectTrigger
        className="w-[110px] h-8 bg-black/40 border-white/20 text-white text-xs"
        aria-label="Video quality"
        data-testid="quality-selector"
      >
        <SelectValue placeholder="Quality" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="auto">Auto</SelectItem>
        {levels.map((level) => (
          <SelectItem key={level.index} value={String(level.index)}>
            {level.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
