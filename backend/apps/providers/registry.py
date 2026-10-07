from apps.providers.magic_hour import MagicHourProvider


class ProviderRegistry:
    _providers = {"magic_hour": MagicHourProvider()}

    @classmethod
    def get(cls, provider_name: str):
        try:
            return cls._providers[provider_name]
        except KeyError:
            raise ValueError(f"Unknown media provider: {provider_name}") from None
