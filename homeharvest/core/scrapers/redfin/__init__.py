import json
from ..models import Property, Address, PropertyType, Building
from .. import Scraper
from typing import Any


class RedfinScraper(Scraper):
    def __init__(self, scraper_input):
        super().__init__(scraper_input)
        self.listing_type = scraper_input.listing_type

    def _handle_location(self):
        url = "https://www.redfin.com/stingray/do/location-autocomplete?v=2&al=1&location={}".format(
            self.location
        )

        response = self.session.get(url)
        response_json = json.loads(response.text.replace("{}&&", ""))

        def get_region_type(match_type: str):
            if match_type == "4":
                return "2"  #: zip
            elif match_type == "2":
                return "6"  #: city
            elif match_type == "1":
                return "address"  #: address, needs to be handled differently

        if response_json["payload"]["exactMatch"] is not None:
            target = response_json["payload"]["exactMatch"]
        else:
            target = response_json["payload"]["sections"][0]["rows"][0]

        return target["id"].split("_")[1], get_region_type(target["type"])

    def _parse_home(self, home: dict, single_search: bool = False) -> Property:
        def get_value(key: str) -> Any | None:
            if key in home and "value" in home[key]:
                return home[key]["value"]

        if not single_search:
            address = Address(
                address_one=get_value("streetLine"),
                city=home["city"],
                state=home["state"],
                zip_code=home["zip"],
            )
        else:
            address_info = home["streetAddress"]

            address = Address(
                address_one=address_info["assembledAddress"],
                city=home["city"],
                state=home["state"],
                zip_code=home["zip"],
            )
        url = "https://www.redfin.com{}".format(home["url"])
        property_type = home["propertyType"] if "propertyType" in home else None
        lot_size_data = home.get("lotSize")
        if not isinstance(lot_size_data, int):
            lot_size = (
                lot_size_data.get("value", None)
                if isinstance(lot_size_data, dict)
                else None
            )
        else:
            lot_size = lot_size_data

        return Property(
            site_name=self.site_name,
            listing_type=self.listing_type,
            address=address,
            url=url,
            beds=home["beds"] if "beds" in home else None,
            baths=home["baths"] if "baths" in home else None,
            stories=home["stories"] if "stories" in home else None,
            agent_name=get_value("listingAgent"),
            description=home["listingRemarks"] if "listingRemarks" in home else None,
            year_built=get_value("yearBuilt")
            if not single_search
            else home["yearBuilt"],
            square_feet=get_value("sqFt"),
            lot_size=lot_size,
            property_type=PropertyType.from_int_code(home.get("propertyType")),
            price_per_square_foot=get_value("pricePerSqFt"),
            price=get_value("price"),
            mls_id=get_value("mlsId"),
        )

    def _parse_building(self, building: dict) -> Building:
        return Building(
            address=Address(
                address_one=" ".join(
                    [
                        building['address']['streetNumber'],
                        building['address']['directionalPrefix'],
                        building['address']['streetName'],
                        building['address']['streetType'],
                    ]
                ),
                city=building['address']['city'],
                state=building['address']['stateOrProvinceCode'],
                zip_code=building['address']['postalCode'],
                address_two=" ".join(
                    [
                        building['address']['unitType'],
                        building['address']['unitValue'],
                    ]
                )
            ),
            site_name=self.site_name,
            url="https://www.redfin.com{}".format(building["url"]),
            listing_type=self.listing_type,
            num_units=building["numUnitsForSale"],
        )


    def handle_address(self, home_id: str):
        """
        EPs:
        https://www.redfin.com/stingray/api/home/details/initialInfo?al=1&path=/TX/Austin/70-Rainey-St-78701/unit-1608/home/147337694
        https://www.redfin.com/stingray/api/home/details/mainHouseInfoPanelInfo?propertyId=147337694&accessLevel=3
        https://www.redfin.com/stingray/api/home/details/aboveTheFold?propertyId=147337694&accessLevel=3
        https://www.redfin.com/stingray/api/home/details/belowTheFold?propertyId=147337694&accessLevel=3
        """

        url = "https://www.redfin.com/stingray/api/home/details/aboveTheFold?propertyId={}&accessLevel=3".format(
            home_id
        )

        response = self.session.get(url)
        response_json = json.loads(response.text.replace("{}&&", ""))

        parsed_home = self._parse_home(
            response_json["payload"]["addressSectionInfo"], single_search=True
        )
        return [parsed_home]

    def search(self):
        region_id, region_type = self._handle_location()

        if region_type == "address":
            home_id = region_id
            return self.handle_address(home_id)

        url = "https://www.redfin.com/stingray/api/gis?al=1&region_id={}&region_type={}".format(
            region_id, region_type
        )

        response = self.session.get(url)
        response_json = json.loads(response.text.replace("{}&&", ""))

        homes = [
            self._parse_home(home) for home in response_json["payload"]["homes"]
        ] + [
            self._parse_building(building) for building in response_json["payload"]["buildings"].values()
        ]

        return homes
