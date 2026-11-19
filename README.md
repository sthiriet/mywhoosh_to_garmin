# MyWhoosh vers Garmin Connect

Synchronise les activités MyWhoosh absentes de Garmin Connect.

Le programme récupère les activités MyWhoosh des sept derniers jours,
compare leurs horaires UTC et leurs distances aux activités Garmin, puis
télécharge vers Garmin les activités absentes après modification du fichier FIT.

## Prérequis

- Python 3.9 ou supérieur
- Un compte MyWhoosh
- Un compte Garmin Connect
- Les identifiants FIT correspondant à votre appareil Garmin

## Installation

```bash
git clone <URL_DU_DEPOT>
cd mywhoosh-to-garmin

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cp config.example.json config.json
chmod 600 config.json
```

## Configuration

Modifiez `config.json` :

```json
{
  "mywhoosh_email": "votre-adresse@example.com",
  "mywhoosh_password": "votre-mot-de-passe",
  "garmin_email": "votre-adresse@example.com",
  "garmin_password": "votre-mot-de-passe",
  "token_dir": ".",
  "manufacturer_id": 1,
  "product_id": 4315,
  "serial_number": 1123456789
}
```

Les trois identifiants FIT sont écrits dans les messages `file_id` et
`device_info` :

| Champ | Format | Exemple |
| --- | --- | --- |
| `manufacturer_id` | entier entre 0 et 65535 | `1` |
| `product_id` | entier entre 0 et 65535 | `4315` |
| `serial_number` | entier entre 0 et 4294967295 | `1123456789` |

Utilisez les identifiants correspondant à votre appareil Garmin.

Pour retrouver les valeurs depuis un fichier FIT existant enregistré avec votre
appareil principal :

```bash
.venv/bin/python read_fit.py chemin/vers/activité.fit
```

Le script affiche :

```text
manufacturer_id: 1
product_id:      4315
serial_number:   1123456789
```

Les valeurs obtenues peuvent ensuite être copiées dans `config.json`. Si un
champ est absent du FIT, le script affiche `None`. Utilisez de préférence un
fichier d'activité provenant directement de l'appareil ciblé.

`token_dir` définit le dossier commun contenant les jetons :

```text
token_dir/
├── mywhoosh_token.json
├── oauth1_token.json
└── oauth2_token.json
```

Utilisez un chemin absolu si le programme est lancé depuis une tâche planifiée
ou un service.

## Premier lancement

```bash
.venv/bin/python main.py
```

Au premier lancement, les identifiants peuvent être utilisés pour obtenir les
jetons. Les lancements suivants utilisent les jetons mis en cache.

Ne partagez jamais `config.json` ni les fichiers OAuth. Ils sont ignorés par
Git grâce au `.gitignore`.

## Jetons existants

Le dossier `token_dir` peut recevoir les trois jetons d'une installation déjà
authentifiée :

```text
mywhoosh_token.json
oauth1_token.json
oauth2_token.json
```

Restreignez leurs droits :

```bash
chmod 600 mywhoosh_token.json oauth1_token.json oauth2_token.json
```

Une ancienne copie située dans `garmin-tokens/` est migrée automatiquement
vers `token_dir` au démarrage.

## Planification

Avec `cron`, par exemple toutes les six heures :

```cron
CRON_TZ=Europe/Paris
0 */6 * * * flock -n /tmp/mywhoosh-to-garmin.lock -c 'cd /chemin/vers/mywhoosh-to-garmin && /chemin/vers/mywhoosh-to-garmin/.venv/bin/python main.py 2>&1 | /usr/bin/logger -t mywhoosh-to-garmin'
```

Adaptez les chemins, le fuseau horaire et la fréquence.

Sur les systèmes utilisant `systemd-journald`, consultez les logs avec :

```bash
journalctl -t mywhoosh-to-garmin --since "today"
```

`flock -n` évite les exécutions simultanées. Une fréquence toutes les quelques
heures est préférable à des lancements fréquents.

## Déduplication

Une activité MyWhoosh est considérée comme déjà présente sur Garmin lorsque :

- l'écart UTC est inférieur ou égal à 5 minutes ;
- l'écart de distance est inférieur ou égal à 500 mètres.

## Dépannage

### HTTP 429

Garmin limite temporairement les requêtes. Attendez avant de relancer le
programme. Conservez les jetons OAuth valides et évitez les exécutions
simultanées ou rapprochées.

### Configuration FIT invalide

Les identifiants FIT doivent être des entiers dans les plages indiquées. Le
programme refuse les valeurs négatives, hors limites ou non numériques.

### Jetons expirés

Après vérification, supprimez uniquement les jetons concernés puis relancez une
fois avec les identifiants configurés :

```bash
rm -f mywhoosh_token.json oauth1_token.json oauth2_token.json
.venv/bin/python main.py
```

## Sécurité

- Ne commitez jamais `config.json`
- Ne commitez jamais les fichiers de jeton
- Utilisez des permissions `600` pour les mots de passe et jetons
- Ne publiez jamais les fichiers FIT contenant des données d'activité
