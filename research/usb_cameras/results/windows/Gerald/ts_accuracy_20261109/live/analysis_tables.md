| run | camera | fps | drops | grab-mid vs lattice std/p95/max | post-ret vs lattice std/p95/max | fitted vs own line std | stale | gate wait med/p95 |
|---|---|---|---|---|---|---|---|---|
| A1_c922 | C922 | 30.000 | 0 | 4.62/7.56/8.45 | 4.61/7.54/8.38 | 0.074 | 0.00 | 0.0/0.0 |
| A1_c930e | C930e | 30.085 | 0 | 5.65/10.04/47.37 | 5.40/9.88/18.18 | 0.110 | 0.00 | 0.0/0.0 |
| A2 | C930e | 30.082 | 3 | 16.19/29.62/35.84 | 7.29/15.38/25.50 | 0.747 | 0.54 | 30.6/34.7 |
| A2 | KiyoPro | 30.019 | 0 | 7.59/17.63/31.01 | 4.71/7.86/10.19 | 0.002 | 0.00 | 0.0/12.7 |
| A3 | Generic | 25.757 | 0 | 4.70/7.73/10.86 | 4.69/7.69/10.67 | 0.113 | 0.00 | 0.0/0.0 |
| A3 | C930e | 30.085 | 320 | 12.96/23.90/41.10 | 12.47/23.08/32.15 | 0.561 | 0.96 | 31.6/47.6 |
| A4 | C922 | 30.015 | 1 | 16.13/34.91/45.77 | 14.79/34.18/37.48 | 7.294 | 0.01 | 0.0/14.9 |
| A4 | C930e | 30.093 | 6 | 20.56/39.09/59.64 | 15.73/26.99/44.57 | 5.614 | 0.28 | 17.7/33.6 |
| A4 | KiyoPro | 30.032 | 2 | 12.24/21.29/68.14 | 15.06/34.38/56.83 | 4.199 | 0.09 | 19.0/31.8 |
| B1_c922 | C922 | 30.001 | 0 | 4.63/7.61/10.60 | 4.63/7.61/10.57 | 0.072 | 0.00 | 0.0/0.0 |
| B1_c930e | C930e | 30.085 | 0 | 4.67/7.69/10.50 | 4.66/7.69/10.42 | 0.022 | 0.00 | 0.0/0.0 |
| B2 | C930e | 30.085 | 0 | 4.79/7.93/13.83 | 4.78/7.90/13.83 | 0.298 | 0.00 | 0.0/0.0 |
| B2 | KiyoPro | 30.019 | 0 | 4.71/7.94/10.36 | 4.71/7.91/10.23 | 0.100 | 0.00 | 0.0/0.0 |
| B3 | Generic | 25.757 | 0 | 4.63/7.60/8.71 | 4.63/7.59/8.75 | 0.010 | 0.00 | 0.0/0.0 |
| B3 | C930e | 30.085 | 0 | 4.65/7.69/9.80 | 4.65/7.66/9.85 | 0.037 | 0.00 | 0.0/0.0 |

| run | camera | fps | drops | sample std/p95/max | arrival std/p95/max | ref clock | clock lattice std us | sample vs clock | arrival vs clock | fitted vs clock |
|---|---|---|---|---|---|---|---|---|---|---|
| mf_c922 | C922 | 30.000 | 0 | 4.60/7.93/7.99 | 4.62/7.66/8.12 | - | - | - | - | - |
| mf_c930e | C930e | 30.085 | 0 | 4.63/7.61/9.35 | 4.63/7.62/10.12 | - | - | - | - | - |
| mf_c930e_generic | C930e | 30.085 | 0 | 4.63/7.64/9.14 | 4.64/7.64/10.13 | - | - | - | - | - |
| mf_c930e_generic | Generic | 25.757 | 0 | 4.62/7.60/8.03 | 4.62/7.61/8.09 | - | - | - | - | - |
| mf_c930e_kiyo | C930e | 30.085 | 0 | 4.63/7.61/9.88 | 4.63/7.59/8.99 | - | - | - | - | - |
| mf_c930e_kiyo | KiyoPro | 30.019 | 0 | 4.73/7.94/10.49 | 4.73/7.93/10.55 | - | - | - | - | - |
| mf_generic | Generic | 25.757 | 0 | 4.61/7.59/8.02 | 4.62/7.60/8.50 | - | - | - | - | - |
| mf_kiyo | KiyoPro | 30.019 | 0 | 4.72/7.89/10.52 | 5.30/7.93/85.31 | pts | 1006.56 | 4.61/7.59/8.58 | 5.20/7.63/83.58 | 1.01/2.22/3.29 |
| mf_smoke6s_c930e_kiyo_meta | C930e | 30.061 | 0 | 4.60/7.55/8.09 | 4.58/7.63/8.47 | pts | 1.35 | 4.60/7.55/8.09 | 4.58/7.63/8.47 | 0.10/0.16/0.17 |
| mf_smoke6s_c930e_kiyo_meta | KiyoPro | 30.002 | 0 | 4.57/7.96/8.01 | 4.54/7.60/8.26 | stc | 952.2 | 4.70/8.15/9.78 | 4.68/8.22/10.30 | 1.03/1.99/2.58 |

A2 C930e-KiyoPro: by-index lattice diff med -27.059 [-52.428, 25.917] first 25.917 last -34.213; stored diff med 0.21 std 0.23; stored-lattice std 19.909 p95 48.88 min -26.107 max 52.75
A3 Generic-C930e: by-index lattice diff med 56.431 [17.894, 80.699] first 39.695 last 53.173; stored diff med -0.236 std 0.155; stored-lattice std 11.284 p95 -38.645 min -80.916 max -18.328
A4 C922-C930e: by-index lattice diff med 26.385 [-15.035, 75.661] first -9.777 last 35.021; stored diff med -0.18 std 1.505; stored-lattice std 21.791 p95 7.302 min -81.844 max 24.335
A4 C922-KiyoPro: by-index lattice diff med 10.751 [-6.261, 38.279] first -6.261 last 4.917; stored diff med -0.183 std 1.666; stored-lattice std 11.742 p95 4.127 min -68.955 max 21.37
A4 C930e-KiyoPro: by-index lattice diff med -16.781 [-46.024, 28.723] first 3.516 last -30.104; stored diff med -0.001 std 1.48; stored-lattice std 15.848 p95 38.074 min -40.328 max 56.969
B2 C930e-KiyoPro: by-index lattice diff med -74.727 [-156.215, 6.761] first 6.761 last -156.215; stored diff med -72.265 std 47.932; stored-lattice std 6.765 p95 11.401 min -17.497 max 21.287
B3 Generic-C930e: by-index lattice diff med 5466.997 [152.988, 10781.005] first 152.988 last 10781.005; stored diff med 5469.482 std 3069.674; stored-lattice std 6.579 p95 10.874 min -15.946 max 15.996
mf_c930e_generic C930e-Generic: by-index lattice diff med -4523.534 [-9695.144, 648.076] first 648.076 last -9695.144; stored diff med -4520.004 std 2987.408; stored-lattice std 6.519 p95 10.937 min -15.692 max 15.648
mf_c930e_kiyo C930e-KiyoPro: by-index lattice diff med -399.352 [-477.275, -321.429] first -321.429 last -477.275; stored diff med -396.001 std 45.639; stored-lattice std 6.741 p95 10.986 min -16.834 max 16.605
mf_smoke6s_c930e_kiyo_meta C930e-KiyoPro: by-index lattice diff med -80.381 [-81.591, -79.171] first -79.171 last -81.591; stored diff med -88.042 std 7.987; stored-lattice std 7.892 p95 9.016 min -8.778 max 9.483
