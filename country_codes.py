import re
import unicodedata


# ISO 3166-1 alpha-2 codes used for storage. Display names stay outside the DB.
COUNTRY_NAMES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Aland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin",
    "BL": "Saint Barthelemy", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia",
    "BQ": "Caribbean Netherlands", "BR": "Brazil", "BS": "Bahamas", "BT": "Bhutan",
    "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus", "BZ": "Belize",
    "CA": "Canada", "CC": "Cocos Islands", "CD": "DR Congo",
    "CF": "Central African Republic", "CG": "Republic of the Congo", "CH": "Switzerland",
    "CI": "Cote d'Ivoire", "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon",
    "CN": "China", "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba",
    "CV": "Cabo Verde", "CW": "Curacao", "CX": "Christmas Island", "CY": "Cyprus",
    "CZ": "Czechia", "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark",
    "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji",
    "FK": "Falkland Islands", "FM": "Micronesia", "FO": "Faroe Islands", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia",
    "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar",
    "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala", "GU": "Guam",
    "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras", "HR": "Croatia",
    "HT": "Haiti", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IM": "Isle of Man", "IN": "India",
    "IO": "British Indian Ocean Territory", "IQ": "Iraq", "IR": "Iran", "IS": "Iceland",
    "IT": "Italy", "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan",
    "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati",
    "KM": "Comoros", "KN": "Saint Kitts and Nevis", "KP": "North Korea",
    "KR": "South Korea", "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MF": "Saint Martin",
    "MG": "Madagascar", "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali",
    "MM": "Myanmar", "MN": "Mongolia", "MO": "Macau", "MP": "Northern Mariana Islands",
    "MQ": "Martinique", "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta",
    "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi", "MX": "Mexico",
    "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia",
    "NE": "Niger", "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua",
    "NL": "Netherlands", "NO": "Norway", "NP": "Nepal", "NR": "Nauru", "NU": "Niue",
    "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PM": "Saint Pierre and Miquelon",
    "PN": "Pitcairn Islands", "PR": "Puerto Rico", "PS": "Palestine", "PT": "Portugal",
    "PW": "Palau", "PY": "Paraguay", "QA": "Qatar", "RE": "Reunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden",
    "SG": "Singapore", "SH": "Saint Helena", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South Sudan", "ST": "Sao Tome and Principe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini", "TC": "Turks and Caicos Islands",
    "TD": "Chad", "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand",
    "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan",
    "TN": "Tunisia", "TO": "Tonga", "TR": "Turkiye", "TT": "Trinidad and Tobago",
    "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "U.S. Minor Outlying Islands", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "Saint Vincent and the Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa",
    "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
    # Widely used user-assigned code for Kosovo, which has no ISO alpha-2 assignment.
    "XK": "Kosovo",
}


def _token(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    plain_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W_]+", plain_text, flags=re.UNICODE))


_ALIASES = {_token(name): code for code, name in COUNTRY_NAMES.items()}
_ALIASES.update({
    "america": "US", "u s": "US", "u s a": "US", "usa": "US",
    "united states of america": "US", "uk": "GB", "u k": "GB", "great britain": "GB",
    "uae": "AE", "u a e": "AE", "republic of korea": "KR", "korea south": "KR",
    "korea republic of": "KR", "democratic people s republic of korea": "KP",
    "korea north": "KP", "russian federation": "RU", "viet nam": "VN",
    "macao": "MO", "hong kong sar": "HK", "hong kong sar china": "HK",
    "hong kong china": "HK", "mainland china": "CN", "people s republic of china": "CN",
    "taiwan province of china": "TW", "republic of china": "TW",
    "netherlands kingdom of the": "NL", "the netherlands": "NL",
    "czech republic": "CZ", "turkey": "TR", "swaziland": "SZ", "cape verde": "CV",
    "ivory coast": "CI", "brunei darussalam": "BN", "lao people s democratic republic": "LA",
    "moldova republic of": "MD", "bolivia plurinational state of": "BO",
    "iran islamic republic of": "IR", "tanzania united republic of": "TZ",
    "venezuela bolivarian republic of": "VE", "syrian arab republic": "SY",
    "micronesia federated states of": "FM", "palestinian territories": "PS",
    "state of palestine": "PS", "congo democratic republic of the": "CD",
    "democratic republic of the congo": "CD", "congo kinshasa": "CD",
    "congo brazzaville": "CG", "republic of congo": "CG", "bahamas the": "BS",
    "gambia the": "GM", "north macedonia republic of": "MK",
    "saint martin french part": "MF", "sint maarten dutch part": "SX",
    "curacao country of": "CW", "caribbean netherlands bonaire sint eustatius and saba": "BQ",
    "kosovo": "XK",
    "대한민국": "KR", "한국": "KR", "홍콩": "HK", "중국": "CN", "마카오": "MO",
    "대만": "TW", "일본": "JP", "미국": "US", "영국": "GB", "프랑스": "FR",
    "독일": "DE", "이탈리아": "IT", "스페인": "ES", "네덜란드": "NL",
    "벨기에": "BE", "덴마크": "DK", "노르웨이": "NO", "스웨덴": "SE",
    "스위스": "CH", "오스트리아": "AT", "포르투갈": "PT", "포르투칼": "PT",
    "호주": "AU", "오스트레일리아": "AU", "캐나다": "CA", "싱가포르": "SG",
    "태국": "TH",
})
_ALIASES = {_token(alias): code for alias, code in _ALIASES.items()}

_TAIWAN_HINTS = ("taiwan", "taipei", "kaohsiung", "taichung", "tainan", "hsinchu", "keelung", "taoyuan")


def normalize_country_code(value, city="", address="", region=""):
    raw = str(value or "").strip()
    upper = raw.upper()
    if len(upper) == 2 and upper in COUNTRY_NAMES:
        return upper

    token = _token(raw)
    if token == "greater china":
        hints = _token(" ".join((str(city or ""), str(address or ""), str(region or ""))))
        if "hong kong" in hints:
            return "HK"
        if "macau" in hints or "macao" in hints:
            return "MO"
        if any(hint in hints for hint in _TAIWAN_HINTS):
            return "TW"
        return "CN"
    return _ALIASES.get(token, "")


def country_display_name(value, city="", address="", region=""):
    code = normalize_country_code(value, city=city, address=address, region=region)
    return COUNTRY_NAMES.get(code, str(value or "").strip())


def country_values_match(left, right, left_city="", left_address="", left_region=""):
    left_code = normalize_country_code(
        left, city=left_city, address=left_address, region=left_region
    )
    right_code = normalize_country_code(right)
    if left_code and right_code:
        return left_code == right_code
    return _token(left) == _token(right)
