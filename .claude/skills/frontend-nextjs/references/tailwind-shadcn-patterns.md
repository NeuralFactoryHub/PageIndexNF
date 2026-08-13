# Tailwind & shadcn/ui Patterns

## shadcn/ui Components Available

Located in `components/ui/`:
- `button` — primary action buttons
- `card` (Card, CardContent, CardHeader, CardTitle) — section containers
- `checkbox` — skill selection, toggles
- `input` — form text fields
- `label` — form labels
- `select` (Select, SelectContent, SelectItem, SelectTrigger, SelectValue) — dropdowns
- `slider` — range inputs

All use **New York style** variant with Radix primitives.

## Common Layout Patterns

```jsx
// Card-based sections
<Card>
  <CardHeader>
    <CardTitle className="flex items-center gap-2">
      <Icon className="h-5 w-5" />
      Section Title
    </CardTitle>
  </CardHeader>
  <CardContent>
    {/* content */}
  </CardContent>
</Card>

// Grid layouts
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  {/* stat cards */}
</div>
```

## Icons

```jsx
import { Users, Cog, Calendar, LayoutDashboard, Factory } from 'lucide-react';
// Always lucide-react, consistent h-5 w-5 sizing
```

## cn() Helper

```typescript
// lib/utils.ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

## Responsive Conventions

- Mobile-first with `sm:`, `md:`, `lg:` breakpoints
- Grid columns scale: `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`
- Sidebar/navigation adapts at `lg:` breakpoint
