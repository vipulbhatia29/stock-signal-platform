"use client";

import { useState, useEffect, useRef } from "react";
import { useStockSearch } from "@/hooks/use-stocks";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { SearchIcon, PlusCircleIcon } from "lucide-react";

interface TickerSearchProps {
  onSelect: (ticker: string) => void;
}

export function TickerSearch({ onSelect }: TickerSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => setDebouncedQuery(query), 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query]);

  const { data: results, isLoading } = useStockSearch(debouncedQuery);

  const dbResults = results?.filter((s) => s.in_db) ?? [];
  const externalResults = results?.filter((s) => !s.in_db) ?? [];

  function handleSelect(ticker: string) {
    onSelect(ticker);
    setOpen(false);
    setQuery("");
    setDebouncedQuery("");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={
        <Button
          variant="outline"
          className="w-full max-w-md justify-start gap-2 text-muted-foreground font-normal"
        >
          <SearchIcon className="size-4" />
          Search stocks to add...
        </Button>
      } />
      <PopoverContent className="w-80 p-0 bg-card2 border-border" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search by ticker or name..."
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            {isLoading && debouncedQuery && (
              <div className="py-4 text-center text-sm text-subtle">
                Searching...
              </div>
            )}
            {!isLoading && debouncedQuery && (!results || results.length === 0) && (
              <CommandEmpty>No stocks found</CommandEmpty>
            )}
            {/* Stocks already in our database */}
            {dbResults.length > 0 && (
              <CommandGroup heading="In watchlist universe">
                {dbResults.map((stock) => (
                  <CommandItem
                    key={stock.ticker}
                    value={stock.ticker}
                    onSelect={() => handleSelect(stock.ticker)}
                    className="hover:bg-hov text-foreground"
                  >
                    <div className="flex flex-1 items-center justify-between">
                      <div>
                        <span className="font-mono font-semibold">
                          {stock.ticker}
                        </span>
                        <span className="ml-2 text-muted-foreground">
                          {stock.name}
                        </span>
                      </div>
                      {stock.sector && (
                        <span className="text-xs text-muted-foreground">
                          {stock.sector}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {/* External results from Yahoo Finance — not yet in DB */}
            {externalResults.length > 0 && (
              <CommandGroup heading="Add from market">
                {externalResults.map((stock) => (
                  <CommandItem
                    key={stock.ticker}
                    value={`add-${stock.ticker}`}
                    onSelect={() => handleSelect(stock.ticker)}
                    className="hover:bg-hov text-foreground"
                  >
                    <PlusCircleIcon className="mr-2 size-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex flex-1 items-center justify-between min-w-0">
                      <div className="truncate">
                        <span className="font-mono font-semibold">
                          {stock.ticker}
                        </span>
                        <span className="ml-2 text-muted-foreground">
                          {stock.name}
                        </span>
                      </div>
                      {stock.exchange && (
                        <span className="text-xs text-muted-foreground flex-shrink-0 ml-2">
                          {stock.exchange}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
