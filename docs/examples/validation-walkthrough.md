# Example: Troubleshoot Validation Issues

This example shows how to handle validation failures before saving.

## Scenario

You created two components:

```text
cpu0
cache0
```

The save operation fails because required parameters are missing.

## Validation summary

The save dialog may report:

```text
cpu0: Required parameter 'clock' is missing a value.
cache0: Required parameter 'cache_size' is missing a value.
```

## Fix `cpu0`

1. Click `cpu0`.
2. Look for rows marked with `*` in the properties panel.
3. Fill the missing value:

```text
clock *    2GHz
```

## Fix `cache0`

1. Click `cache0`.
2. Fill missing required values:

```text
cache_size *    32KiB
```

## Duplicate names

If the model contains two nodes with the same name, rename one:

```text
cache0
cache1
```

## Save again

Use:

```text
File -> Save
```

If all issues are fixed, the save completes.
