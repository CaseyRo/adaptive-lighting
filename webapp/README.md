> ### ⚠️ Not used by the CDiT fork
>
> This Shiny webapp is the **upstream** Adaptive Lighting simulator. It
> models the upstream curve (with `brightness_mode`, `brightness_mode_time_*`,
> sleep mode, etc.) — features the CDiT fork has **removed**.
>
> The CDiT fork uses a fixed-tanh curve with a hardcoded 30-minute half-width,
> anchored at the user's configured `sunrise_entity` / `sunset_entity`.
> The simulator's outputs will not match what the integration computes.
>
> Kept here for upstream-merge hygiene. Not built or deployed by the fork's
> CI. See [`../README.md`](../README.md) for the fork's actual behavior.

---

To run this app locally, install the requirements and run `shiny run`.

```
$ cd webapp
$ pip install -r requirements-dev.txt
$ shiny run
```

After the server starts, which should take only a moment, you can open
[http://127.0.0.1:8000](http://127.0.0.1:8000) to see the interface.
