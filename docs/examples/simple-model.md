# Example: Build a Simple Model

This example creates a simple two-component model with one link.

## 1. Start FUSE

```bash
fuse-mod
```

## 2. Add two components

1. Drag a CPU-like component from the palette into the canvas.
2. Drag a cache-like or memory-like component into the canvas.

Rename them in the properties panel:

```text
cpu0
cache0
```

## 3. Configure parameters

Select `cpu0` and fill required values.

Example:

```text
clock    2GHz
threads  4
```

Select `cache0` and fill required values.

Example:

```text
cache_size     32KiB
associativity  8
```

## 4. Create a link

1. Click the output/source port on `cpu0`.
2. Click the input/target port on `cache0`.
3. Enter latency:

```text
1ns
```

## 5. Save the model

Use:

```text
File -> Save As...
```

Save as:

```text
examples/cpu_cache_example.fse
```

## 6. Reopen the model

Use:

```text
File -> Open...
```

Verify:

- Both components are restored.
- Names are preserved.
- Link is restored.
- Parameters are preserved.
- Link latency is preserved.
