import numpy as np
import matplotlib.pyplot as plt


def show_dose_check(cts, masks, dose_on_ct, valid_mask, k, roi_channel):
    ct = cts[k]
    roi = masks[k, roi_channel].astype(bool)
    valid = valid_mask[k].astype(bool)

    if not valid.any():
        raise ValueError(f"На срезе {k} нет перенесённых значений дозы")

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))

    for ax in axes:
        ax.imshow(ct, cmap="gray", vmin=-200, vmax=300)
        if roi.any():
            ax.contour(roi, levels=[0.5], colors="cyan", linewidths=1.5)
        ax.axis("off")

    axes[0].set_title("КТ + контур ROI")

    dose_view = np.ma.masked_where(~valid, dose_on_ct[k])
    image = axes[1].imshow(
        dose_view,
        cmap="turbo",
        alpha=0.5,
        vmin=0,
        vmax=max(float(dose_on_ct[k][valid].max()), 1),
    )

    if (~valid).any():
        axes[1].contour(valid, levels=[0.5], colors="white",
                        linestyles="--", linewidths=1)

    axes[1].set_title("КТ + доза + контур ROI")
    fig.colorbar(image, ax=axes[1], label="Доза, Гр")
    plt.show()

    if roi.any():
        coverage = (roi & valid).sum() / roi.sum()
        print(f"Дозовая сетка покрывает {coverage:.1%} пикселей выбранной ROI")